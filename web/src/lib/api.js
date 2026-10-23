const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8080').replace(/\/$/, '');
const RESULT_STATUSES = new Set(['answered', 'cached', 'blocked', 'failed']);

/** Free hosting sleeps when idle; ping on page load so it is awake by the time the user asks. */
export function warmUpServer() {
  fetch(`${API_URL}/healthz`, { mode: 'cors' }).catch(() => {});
}

export class ApiError extends Error {
  constructor(status, code, message, requestId) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

/** Thin fetch wrapper: attaches the Firebase ID token and normalises errors. */
export function createApi(getToken) {
  async function request(path, { method = 'GET', body, signal } = {}) {
    const token = await getToken();
    let response;
    try {
      response = await fetch(`${API_URL}${path}`, {
        method,
        signal,
        headers: {
          Authorization: `Bearer ${token}`,
          ...(body ? { 'Content-Type': 'application/json' } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (err) {
      if (err?.name === 'AbortError') throw err;
      throw new ApiError(0, 'NETWORK', 'Cannot reach the server. Check your connection and try again.');
    }

    const payload = await response.json().catch(() => ({}));
    // Blocked and failed questions are answers too: they carry a trace and a reason.
    if (response.ok || RESULT_STATUSES.has(payload.status)) return payload;
    throw new ApiError(
      response.status,
      payload.code ?? 'UNKNOWN',
      payload.message ?? `Request failed (${response.status}).`,
      payload.requestId,
    );
  }

  return {
    ask: (question, signal) => request('/api/ask', { method: 'POST', body: { question }, signal }),
    history: () => request('/api/history?limit=20'),
    query: (id) => request(`/api/queries/${encodeURIComponent(id)}`),
    evalLatest: () => request('/api/metrics/eval/latest'),
    live: () => request('/api/metrics/live'),
  };
}
