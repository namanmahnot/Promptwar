import { Router } from 'express';
import { cacheKey, questionHash } from '../lib/hash.js';
import { httpStatusFor, toCachedRecord, toClient, toRecord } from '../lib/present.js';
import { AppError } from '../middleware/errors.js';
import { askLimiters } from '../middleware/rateLimit.js';
import { askSchema, validate } from '../middleware/validate.js';

export function askRouter({ agent, store, config, logger }) {
  const router = Router();

  /** Store failures must never lose the user's answer (docs/04 "Reliability"). */
  async function persist(label, requestId, fn, fallback) {
    try {
      return await fn();
    } catch (err) {
      logger.error(`${label} failed`, { requestId, error: err.message });
      return fallback;
    }
  }

  router.post('/ask', ...askLimiters(), validate(askSchema), async (req, res) => {
    const { question } = req.valid.body;
    const { uid } = req.user;
    const requestId = req.id;
    const started = performance.now();
    const elapsed = () => Math.round(performance.now() - started);
    const key = cacheKey(question, config.modelSql, config.promptVersion);

    persist('user upsert', requestId, () => store.upsertUser(req.user));

    const hit = await persist('cache lookup', requestId, () => store.findCached(key), null);
    if (hit) {
      const record = toCachedRecord(hit, { requestId, uid, question, latencyMs: elapsed() });
      const saved = await persist('audit write', requestId, () => store.saveQuery(record), record);
      logger.info('ask', { requestId, uid, status: 'cached', ms: record.latencyMs });
      return res.status(200).json(toClient(saved));
    }

    const context = {
      requestId,
      uid,
      question,
      questionHash: questionHash(question),
      model: config.modelSql,
      promptVersion: config.promptVersion,
    };

    let result;
    try {
      result = await agent.ask({ question, uid, requestId });
    } catch (err) {
      if (err instanceof AppError) {
        const failed = toRecord({ status: 'failed', code: err.code, message: err.message }, { ...context, latencyMs: elapsed() });
        await persist('audit write', requestId, () => store.saveQuery(failed));
      }
      throw err;
    }

    const record = toRecord(result, { ...context, latencyMs: elapsed() });
    const saved = await persist('audit write', requestId, () => store.saveQuery(record), record);
    if (record.status === 'answered' && saved._id) {
      await persist('cache write', requestId, () => store.saveCache(key, saved._id, config.cacheTtlMs));
    }

    logger.info('ask', {
      requestId,
      uid,
      status: record.status,
      code: record.code,
      ms: record.latencyMs,
      bytes: record.bytesProcessed,
      model: record.llm.model,
    });
    return res.status(httpStatusFor(record)).json(toClient(saved, result.data?.rows));
  });

  return router;
}
