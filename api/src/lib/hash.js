import { createHash } from 'node:crypto';

/** Lowercase, trim, collapse whitespace, strip trailing punctuation (docs/04 "Efficiency levers"). */
export function normalizeQuestion(question) {
  return question
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[\s?.!;,]+$/, '');
}

export function questionHash(question) {
  return createHash('sha256').update(normalizeQuestion(question)).digest('hex');
}

export function cacheKey(question, model, promptVersion) {
  return createHash('sha256')
    .update(`${normalizeQuestion(question)}\n${model}\n${promptVersion}`)
    .digest('hex');
}
