import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';
import { AppError } from '../src/middleware/errors.js';
import { answeredResult, fakeAgent, startServer } from './helpers.js';

let ctx;
afterEach(async () => {
  await ctx?.close();
  ctx = undefined;
});

const ask = (question, token = 'token-alice') => ctx.request('/api/ask', { method: 'POST', token, body: { question } });

describe('health and authentication', () => {
  it('serves /healthz without a token', async () => {
    ctx = await startServer();
    const res = await ctx.request('/healthz');
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { ok: true });
  });

  it('rejects /api calls without a token with 401 AUTH_REQUIRED', async () => {
    ctx = await startServer();
    const res = await ctx.request('/api/ask', { method: 'POST', body: { question: 'Top categories' } });
    assert.equal(res.status, 401);
    assert.equal((await res.json()).code, 'AUTH_REQUIRED');
    assert.equal(ctx.agent.calls.length, 0);
  });

  it('rejects an invalid token', async () => {
    ctx = await startServer();
    const res = await ask('Top categories', 'forged');
    assert.equal(res.status, 401);
  });

  it('takes the uid from the token, never from the body', async () => {
    ctx = await startServer();
    await ctx.request('/api/ask', { method: 'POST', token: 'token-alice', body: { question: 'Top categories' } });
    assert.equal(ctx.agent.calls[0].uid, 'alice');
  });

  it('sets security headers and a request id', async () => {
    ctx = await startServer();
    const res = await ctx.request('/healthz');
    assert.ok(res.headers.get('x-request-id'));
    assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
    assert.equal(res.headers.get('x-powered-by'), null);
  });
});

describe('input validation', () => {
  it('rejects non-string questions (NoSQL injection shape)', async () => {
    ctx = await startServer();
    const res = await ctx.request('/api/ask', { method: 'POST', token: 'token-alice', body: { question: { $gt: '' } } });
    assert.equal(res.status, 400);
    assert.equal((await res.json()).code, 'VALIDATION_ERROR');
  });

  it('rejects too short, too long and extra fields', async () => {
    ctx = await startServer();
    assert.equal((await ask('hi')).status, 400);
    assert.equal((await ask('x'.repeat(501))).status, 400);
    const extra = await ctx.request('/api/ask', {
      method: 'POST',
      token: 'token-alice',
      body: { question: 'Top categories', uid: 'bob' },
    });
    assert.equal(extra.status, 400);
    assert.equal(ctx.agent.calls.length, 0);
  });

  it('strips control characters before validating', async () => {
    ctx = await startServer();
    await ask('Top\u0000 categories\u0007 by revenue');
    assert.equal(ctx.agent.calls[0].question, 'Top categories by revenue');
  });

  it('rejects malformed JSON and oversized bodies', async () => {
    ctx = await startServer();
    const bad = await ctx.request('/api/ask', { method: 'POST', token: 'token-alice', body: '{not json' });
    assert.equal(bad.status, 400);
    const big = await ctx.request('/api/ask', {
      method: 'POST',
      token: 'token-alice',
      body: { question: 'x'.repeat(20_000) },
    });
    assert.equal(big.status, 413);
  });
});

describe('POST /api/ask', () => {
  it('returns the answer, caps rows at 200 and writes one audit record', async () => {
    ctx = await startServer();
    const res = await ask('Top categories by revenue');
    const body = await res.json();

    assert.equal(res.status, 200);
    assert.equal(body.status, 'answered');
    assert.equal(body.cached, false);
    assert.equal(body.data.rows.length, 200);
    assert.equal(body.data.truncated, true);
    assert.equal(body.metrics.llmCalls, 2);
    assert.ok(body.queryId);

    assert.equal(ctx.store.queries.length, 1);
    const audit = ctx.store.queries[0];
    assert.equal(audit.uid, 'alice');
    assert.equal(audit.rowsPreview.length, 50);
    assert.equal(audit.bqJobId, 'job_1');
    assert.equal(audit.promptVersion, 'v1');
  });

  it('serves a repeated question from cache with 0 LLM calls and 0 bytes', async () => {
    ctx = await startServer();
    await ask('Top categories by revenue');
    const res = await ask('  top categories BY revenue?  ');
    const body = await res.json();

    assert.equal(body.status, 'cached');
    assert.equal(body.cached, true);
    assert.equal(body.metrics.llmCalls, 0);
    assert.equal(body.metrics.bytesProcessed, 0);
    assert.equal(ctx.agent.calls.length, 1);
    assert.equal(ctx.store.queries.length, 2);
  });

  it('maps blocked answers to 422 with the reason code and does not cache them', async () => {
    const blocked = answeredResult({
      status: 'blocked',
      code: 'UNSAFE_SQL',
      message: 'Query references a restricted column (users.email).',
      answer: null,
      data: null,
    });
    ctx = await startServer({ agent: fakeAgent([blocked]) });
    const res = await ask('Show customer emails');
    const body = await res.json();

    assert.equal(res.status, 422);
    assert.equal(body.code, 'UNSAFE_SQL');
    assert.equal(body.answer, null);
    await ask('Show customer emails');
    assert.equal(ctx.agent.calls.length, 2);
  });

  it('maps agent failures to their HTTP codes', async () => {
    const failed = answeredResult({ status: 'failed', code: 'LLM_UNAVAILABLE', answer: null, data: null });
    ctx = await startServer({ agent: fakeAgent([failed]) });
    assert.equal((await ask('Top categories')).status, 503);
  });

  it('returns 504 TIMEOUT and still audits when the agent times out', async () => {
    ctx = await startServer({ agent: fakeAgent([new AppError('TIMEOUT')]) });
    const res = await ask('Top categories');
    assert.equal(res.status, 504);
    assert.equal((await res.json()).code, 'TIMEOUT');
    assert.equal(ctx.store.queries[0].status, 'failed');
  });

  it('still returns the answer when the audit write fails', async () => {
    ctx = await startServer();
    ctx.store.saveQuery = async () => {
      throw new Error('mongo down');
    };
    const res = await ask('Top categories');
    assert.equal(res.status, 200);
    assert.equal((await res.json()).status, 'answered');
  });

  it('rate limits at 10 asks per minute per user with Retry-After', async () => {
    ctx = await startServer();
    for (let i = 0; i < 10; i += 1) assert.equal((await ask(`Question number ${i}`)).status, 200);
    const limited = await ask('One more question');
    assert.equal(limited.status, 429);
    assert.equal((await limited.json()).code, 'RATE_LIMITED');
    assert.ok(Number(limited.headers.get('retry-after')) > 0);
    assert.equal((await ask('Bob is unaffected', 'token-bob')).status, 200);
  });
});

describe('history and ownership', () => {
  it('lists only my questions, newest first', async () => {
    ctx = await startServer();
    await ask('First question');
    await ask('Second question');
    await ask('Bob question', 'token-bob');

    const body = await (await ctx.request('/api/history', { token: 'token-alice' })).json();
    assert.deepEqual(
      body.items.map((i) => i.question),
      ['Second question', 'First question'],
    );
  });

  it('returns 403 for another user\'s query and 400 for a malformed id', async () => {
    ctx = await startServer();
    const { queryId } = await (await ask('Alice question')).json();

    assert.equal((await ctx.request(`/api/queries/${queryId}`, { token: 'token-alice' })).status, 200);
    assert.equal((await ctx.request(`/api/queries/${queryId}`, { token: 'token-bob' })).status, 403);
    assert.equal((await ctx.request('/api/queries/not-an-id', { token: 'token-alice' })).status, 400);
  });
});

describe('metrics and admin', () => {
  it('reports live aggregates', async () => {
    ctx = await startServer();
    await ask('Top categories');
    await ask('Top categories');
    const live = await (await ctx.request('/api/metrics/live', { token: 'token-alice' })).json();
    assert.equal(live.count, 2);
    assert.equal(live.byStatus.cached, 1);
    assert.equal(live.cacheHitRate, 0.5);
  });

  it('allows only admins to trigger an eval run', async () => {
    ctx = await startServer();
    const denied = await ctx.request('/api/admin/eval/run', { method: 'POST', token: 'token-alice' });
    assert.equal(denied.status, 403);

    const ok = await ctx.request('/api/admin/eval/run', { method: 'POST', token: 'token-admin' });
    assert.equal(ok.status, 201);
    const latest = await (await ctx.request('/api/metrics/eval/latest', { token: 'token-alice' })).json();
    assert.equal(latest.run.executionAccuracy, 0.85);
  });
});

describe('CORS', () => {
  it('allows the configured origin only', async () => {
    ctx = await startServer();
    const allowed = await ctx.request('/api/ask', {
      method: 'OPTIONS',
      headers: { origin: 'https://insightpilot.web.app' },
    });
    assert.equal(allowed.status, 204);
    assert.equal(allowed.headers.get('access-control-allow-origin'), 'https://insightpilot.web.app');

    const denied = await ctx.request('/api/ask', { method: 'OPTIONS', headers: { origin: 'https://evil.example' } });
    assert.equal(denied.status, 403);
    assert.equal(denied.headers.get('access-control-allow-origin'), null);
  });
});
