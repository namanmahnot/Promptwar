/** Strict CORS: only allowlisted origins, only the methods and headers the web app uses. */
export function cors(allowedOrigins) {
  const allowed = new Set(allowedOrigins);
  return (req, res, next) => {
    const origin = req.get('origin');
    if (origin && allowed.has(origin)) {
      res.set({
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Authorization, Content-Type',
        'Access-Control-Expose-Headers': 'X-Request-Id, Retry-After',
        'Access-Control-Max-Age': '600',
      });
    }
    res.vary('Origin');
    if (req.method === 'OPTIONS') return res.sendStatus(origin && allowed.has(origin) ? 204 : 403);
    return next();
  };
}
