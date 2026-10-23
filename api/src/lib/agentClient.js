import { AppError } from '../middleware/errors.js';

const ASK_TIMEOUT_MS = 45_000;
const EVAL_TIMEOUT_MS = 290_000;

/**
 * Calls the private agent service. In production every call carries a Google-signed ID token
 * for Cloud Run IAM (roles/run.invoker); the optional internal key is defence in depth.
 */
export function createAgentClient({ agentUrl, internalApiKey, useAgentIdToken, fetchImpl = fetch }) {
  let idTokenClient;

  async function authHeaders() {
    const headers = {};
    if (internalApiKey) headers['x-internal-key'] = internalApiKey;
    if (useAgentIdToken) {
      if (!idTokenClient) {
        const { GoogleAuth } = await import('google-auth-library');
        idTokenClient = new GoogleAuth().getIdTokenClient(agentUrl);
      }
      const signed = await (await idTokenClient).getRequestHeaders(agentUrl);
      headers.authorization = typeof signed.get === 'function' ? signed.get('authorization') : signed.Authorization;
    }
    return headers;
  }

  async function post(path, body, requestId, timeoutMs) {
    let response;
    try {
      response = await fetchImpl(`${agentUrl}${path}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-request-id': requestId, ...(await authHeaders()) },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (err) {
      if (err?.name === 'TimeoutError') throw new AppError('TIMEOUT');
      throw new AppError('AGENT_UNAVAILABLE');
    }
    if (response.status === 503) throw new AppError('AGENT_UNAVAILABLE');
    if (!response.ok) throw new AppError('AGENT_ERROR', `Agent responded with HTTP ${response.status}.`);
    return response.json();
  }

  return {
    ask: ({ question, uid, requestId }) => post('/v1/ask', { question, uid, requestId }, requestId, ASK_TIMEOUT_MS),
    runEval: (requestId) => post('/v1/eval/run', {}, requestId, EVAL_TIMEOUT_MS),
  };
}
