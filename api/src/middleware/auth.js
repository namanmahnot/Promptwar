import { AppError } from './errors.js';

const BEARER = /^Bearer ([A-Za-z0-9._-]+)$/;

/**
 * Verifies the Firebase ID token on every request. The uid always comes from the token,
 * never from the request body.
 */
export function authenticate({ verifyToken }) {
  return async (req, res, next) => {
    const match = BEARER.exec(req.get('authorization') ?? '');
    if (!match) return next(new AppError('AUTH_REQUIRED'));
    try {
      const decoded = await verifyToken(match[1]);
      req.user = {
        uid: decoded.uid,
        email: decoded.email ?? null,
        name: decoded.name ?? null,
        admin: decoded.admin === true,
      };
      return next();
    } catch {
      return next(new AppError('AUTH_REQUIRED', 'Your session is invalid or expired. Please sign in again.'));
    }
  };
}

export function requireAdmin(req, res, next) {
  return req.user?.admin ? next() : next(new AppError('FORBIDDEN'));
}

/** Firebase verifier; in development an explicit opt-in accepts the literal token "dev". */
export async function createTokenVerifier(config) {
  const { initializeApp, getApps } = await import('firebase-admin/app');
  const { getAuth } = await import('firebase-admin/auth');
  const app = getApps()[0] ?? initializeApp({ projectId: config.firebaseProjectId });
  const auth = getAuth(app);

  return async (token) => {
    if (config.authDevBypass && token === 'dev') {
      return { uid: 'dev-user', email: 'dev@localhost', name: 'Local developer', admin: true };
    }
    return auth.verifyIdToken(token);
  };
}
