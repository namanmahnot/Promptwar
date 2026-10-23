import { createApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createLogger } from '../src/lib/logger.js';
import { AppError } from '../src/middleware/errors.js';
import { createMemoryStore } from '../src/store/memoryStore.js';

export const USERS = {
  'token-alice': { uid: 'alice', email: 'alice@example.com', name: 'Alice' },
  'token-bob': { uid: 'bob', email: 'bob@example.com', name: 'Bob' },
  'token-admin': { uid: 'root', email: 'root@example.com', name: 'Admin', admin: true },
};

export function answeredResult(overrides = {}) {
  return {
    status: 'answered',
    code: null,
    message: null,
    answer: { insight: 'Jeans led with 1,200.', facts: [{ label: 'Highest revenue', value: 1200 }], assumptions: [] },
    data: {
      columns: [{ name: 'category', type: 'STRING' }, { name: 'revenue', type: 'FLOAT64' }],
      rows: Array.from({ length: 250 }, (_, i) => ({ category: `c${i}`, revenue: i })),
      rowCount: 250,
      truncated: false,
    },
    chart: { type: 'bar', x: 'category', y: 'revenue' },
    sql: 'SELECT 1',
    jobId: 'job_1',
    trace: [{ step: 'execute', status: 'ok', ms: 5, detail: 'ok' }],
    metrics: { latencyMs: 900, bytesProcessed: 1234, llmCalls: 2, inputTokens: 300, outputTokens: 40, attempts: 1 },
    model: 'gemini-3.5-flash',
    promptVersion: 'v1',
    ...overrides,
  };
}

export function fakeAgent(results = [answeredResult()]) {
  const calls = [];
  return {
    calls,
    async ask(body) {
      calls.push(body);
      const next = results.length > 1 ? results.shift() : results[0];
      if (next instanceof AppError) throw next;
      return structuredClone(next);
    },
    async runEval() {
      return { startedAt: new Date().toISOString(), n: 20, executionAccuracy: 0.85, attackBlockRate: 1 };
    },
  };
}

export async function startServer({ agent = fakeAgent(), store = createMemoryStore(), env = {} } = {}) {
  const config = loadConfig({
    NODE_ENV: 'test',
    AGENT_URL: 'http://localhost:8000',
    CORS_ORIGINS: 'https://insightpilot.web.app',
    ...env,
  });
  const verifyToken = async (token) => {
    if (!USERS[token]) throw new Error('invalid token');
    return USERS[token];
  };
  const app = createApp({ config, verifyToken, agent, store, logger: createLogger({ silent: true }) });
  const server = await new Promise((resolve) => {
    const s = app.listen(0, () => resolve(s));
  });
  const base = `http://127.0.0.1:${server.address().port}`;

  const request = (path, { token, method = 'GET', body, headers = {} } = {}) =>
    fetch(`${base}${path}`, {
      method,
      headers: {
        ...(token ? { authorization: `Bearer ${token}` } : {}),
        ...(body !== undefined ? { 'content-type': 'application/json' } : {}),
        ...headers,
      },
      body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
    });

  return { request, agent, store, close: () => new Promise((resolve) => server.close(resolve)) };
}
