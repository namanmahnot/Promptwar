/** Error codes and HTTP statuses from docs/02-architecture-api.md "Error codes". */
export const ERROR_STATUS = {
  AUTH_REQUIRED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  VALIDATION_ERROR: 400,
  PAYLOAD_TOO_LARGE: 413,
  RATE_LIMITED: 429,
  OUT_OF_SCOPE: 422,
  UNSAFE_REQUEST: 422,
  UNSAFE_SQL: 422,
  COST_LIMIT: 422,
  SQL_FAILED: 502,
  AGENT_ERROR: 502,
  LLM_UNAVAILABLE: 503,
  AGENT_UNAVAILABLE: 503,
  SCHEMA_UNAVAILABLE: 503,
  TIMEOUT: 504,
  INTERNAL: 500,
};

const DEFAULT_MESSAGES = {
  AUTH_REQUIRED: 'Sign in to continue.',
  FORBIDDEN: 'You do not have access to this resource.',
  NOT_FOUND: 'Not found.',
  VALIDATION_ERROR: 'The request is invalid.',
  PAYLOAD_TOO_LARGE: 'The request body is too large.',
  RATE_LIMITED: 'Too many questions. Please wait a moment and try again.',
  TIMEOUT: 'The analysis took too long. Please try a simpler question.',
  AGENT_UNAVAILABLE: 'The analysis service is unavailable. Please try again shortly.',
  AGENT_ERROR: 'The analysis service returned an error.',
  INTERNAL: 'Something went wrong.',
};

export class AppError extends Error {
  constructor(code, message, details) {
    super(message ?? DEFAULT_MESSAGES[code] ?? code);
    this.code = code;
    this.status = ERROR_STATUS[code] ?? 500;
    this.details = details;
  }
}

export function statusForCode(code) {
  return ERROR_STATUS[code] ?? 500;
}

export function notFound(req, res, next) {
  next(new AppError('NOT_FOUND'));
}

export function errorHandler(logger) {
  // Express identifies error handlers by arity, so `next` must stay in the signature.
  return (err, req, res, next) => {
    let error = err;
    if (err?.type === 'entity.parse.failed') error = new AppError('VALIDATION_ERROR', 'Body must be valid JSON.');
    if (err?.type === 'entity.too.large') error = new AppError('PAYLOAD_TOO_LARGE');
    if (!(error instanceof AppError)) {
      logger.error('unhandled error', { requestId: req.id, error: err?.message, stack: err?.stack });
      error = new AppError('INTERNAL');
    }
    if (error.retryAfter) res.set('Retry-After', String(error.retryAfter));
    res.status(error.status).json({
      status: 'error',
      code: error.code,
      message: error.message,
      ...(error.details ? { details: error.details } : {}),
      requestId: req.id,
    });
  };
}
