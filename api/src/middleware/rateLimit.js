import { rateLimit } from 'express-rate-limit';
import { AppError } from './errors.js';

function limiter({ windowMs, limit, keyGenerator }) {
  return rateLimit({
    windowMs,
    limit,
    ...(keyGenerator ? { keyGenerator } : {}), // default: client IP (IPv6 /56 aware)
    standardHeaders: 'draft-8',
    legacyHeaders: false,
    handler: (req, res, next) => {
      const error = new AppError('RATE_LIMITED');
      const resetTime = req.rateLimit?.resetTime;
      error.retryAfter = resetTime ? Math.max(1, Math.ceil((resetTime.getTime() - Date.now()) / 1000)) : 60;
      next(error);
    },
  });
}

/** 300 requests per minute per IP, before authentication. */
export const ipLimiter = () => limiter({ windowMs: 60_000, limit: 300 });

/** 10 asks per minute and 100 per day per signed-in user (docs/01 FR-12). */
export const askLimiters = () => {
  const byUser = (req) => req.user.uid;
  return [
    limiter({ windowMs: 60_000, limit: 10, keyGenerator: byUser }),
    limiter({ windowMs: 24 * 60 * 60_000, limit: 100, keyGenerator: byUser }),
  ];
};
