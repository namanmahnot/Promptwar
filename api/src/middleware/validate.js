import { z } from 'zod';
import { AppError } from './errors.js';

const CONTROL_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g;

export const askSchema = z.strictObject({
  question: z
    .string()
    .transform((q) => q.replace(CONTROL_CHARS, ' ').replace(/\s+/g, ' ').trim())
    .pipe(z.string().min(3, 'Question must be at least 3 characters.').max(500, 'Question must be at most 500 characters.')),
});

export const historyQuerySchema = z.object({
  limit: z.coerce.number().int().min(1).max(50).default(20),
  before: z.iso.datetime().optional(),
});

export const idParamSchema = z.object({
  id: z.string().regex(/^[a-f0-9]{24}$/, 'Invalid id.'),
});

/** Validate and replace `req[source]` with the parsed value; never pass raw input downstream. */
export function validate(schema, source = 'body') {
  return (req, res, next) => {
    const result = schema.safeParse(req[source]);
    if (!result.success) {
      const details = result.error.issues.map((i) => ({ path: i.path.join('.'), message: i.message }));
      return next(new AppError('VALIDATION_ERROR', details[0]?.message, details));
    }
    req.valid = { ...req.valid, [source]: result.data };
    return next();
  };
}
