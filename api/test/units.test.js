import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { loadConfig } from '../src/config.js';
import { createAgentClient } from '../src/lib/agentClient.js';
import { cacheKey, normalizeQuestion } from '../src/lib/hash.js';
import { createLogger } from '../src/lib/logger.js';
import { percentile, summarizeLive } from '../src/lib/metrics.js';
import { askSchema } from '../src/middleware/validate.js';

describe('config', () => {
  it('refuses the auth dev bypass outside development', () => {
    assert.throws(
      () => loadConfig({ NODE_ENV: 'production', AGENT_URL: 'https://a.run.app', AUTH_DEV_BYPASS: 'true' }),
      /AUTH_DEV_BYPASS/,
    );
  });

  it('signs agent calls with an ID token only for https agents', () => {
    assert.equal(loadConfig({ AGENT_URL: 'https://agent.run.app' }).useAgentIdToken, true);
    assert.equal(loadConfig({ AGENT_URL: 'http://localhost:8000' }).useAgentIdToken, false);  });
});

describe('cache key normalisation', () => {
  it('ignores case, whitespace and trailing punctuation', () => {
    assert.equal(normalizeQuestion('  Top   5 Categories?! '), 'top 5 categories');
    assert.equal(cacheKey('Top 5 categories', 'm', 'v1'), cacheKey('top 5   CATEGORIES?', 'm', 'v1'));
  });

  it('changes when the model or prompt version changes', () => {
    assert.notEqual(cacheKey('q', 'm1', 'v1'), cacheKey('q', 'm2', 'v1'));
    assert.notEqual(cacheKey('q', 'm1', 'v1'), cacheKey('q', 'm1', 'v2'));
  });
});

describe('askSchema', () => {
  it('accepts a normal question and trims it', () => {
    assert.deepEqual(askSchema.parse({ question: '  Revenue by month  ' }), { question: 'Revenue by month' });
  });

  for (const [name, body] of [
    ['number', { question: 42 }],
    ['object', { question: { $ne: null } }],
    ['array', { question: ['a', 'b', 'c'] }],
    ['empty', { question: '   ' }],
    ['missing', {}],
  ]) {
    it(`rejects ${name}`, () => assert.equal(askSchema.safeParse(body).success, false));
  }
});

describe('logger redaction', () => {
  it('never prints tokens, keys or authorization headers', () => {
    const lines = [];
    const logger = createLogger({ write: (line) => lines.push(line) });
    logger.info('x', { idToken: 'abc', apiKey: 'k', authorization: 'Bearer t', uid: 'u1' });
    const entry = JSON.parse(lines[0]);
    assert.equal(entry.idToken, '[redacted]');
    assert.equal(entry.apiKey, '[redacted]');
    assert.equal(entry.authorization, '[redacted]');
    assert.equal(entry.uid, 'u1');
  });
});

describe('metrics', () => {
  it('computes nearest-rank percentiles', () => {
    assert.equal(percentile([5, 1, 3, 2, 4], 50), 3);
    assert.equal(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95), 10);
    assert.equal(percentile([], 50), null);
  });

  it('summarises statuses, cache hits and latency', () => {
    const summary = summarizeLive([
      { status: 'answered', latencyMs: 6000, bytesProcessed: 100, llm: { calls: 2 } },
      { status: 'cached', latencyMs: 40, bytesProcessed: 0, llm: { calls: 0 } },
      { status: 'blocked', latencyMs: 10, llm: { calls: 0 } },
    ]);
    assert.equal(summary.cacheHitRate, 0.5);
    assert.equal(summary.p50LatencyMs, 6000);
    assert.equal(summary.p50CachedLatencyMs, 40);
    assert.equal(summary.byStatus.blocked, 1);
  });
});

describe('agent client', () => {
  it('sends the internal key and request id, and maps timeouts to TIMEOUT', async () => {
    let seen;
    const client = createAgentClient({
      agentUrl: 'http://agent',
      internalApiKey: 'k'.repeat(32),
      useAgentIdToken: false,
      fetchImpl: async (url, init) => {
        seen = { url, init };
        return new Response(JSON.stringify({ status: 'answered' }), { status: 200 });
      },
    });
    await client.ask({ question: 'q', uid: 'u', requestId: 'r1' });
    assert.equal(seen.url, 'http://agent/v1/ask');
    assert.equal(seen.init.headers['x-internal-key'], 'k'.repeat(32));
    assert.equal(seen.init.headers['x-request-id'], 'r1');

    const slow = createAgentClient({
      agentUrl: 'http://agent',
      useAgentIdToken: false,
      fetchImpl: async () => {
        throw Object.assign(new Error('timeout'), { name: 'TimeoutError' });
      },
    });
    await assert.rejects(() => slow.ask({ question: 'q', uid: 'u', requestId: 'r' }), { code: 'TIMEOUT' });
  });
});
