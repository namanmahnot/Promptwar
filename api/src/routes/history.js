import { Router } from 'express';
import { toClient } from '../lib/present.js';
import { AppError } from '../middleware/errors.js';
import { historyQuerySchema, idParamSchema, validate } from '../middleware/validate.js';

export function historyRouter({ store }) {
  const router = Router();

  router.get('/history', validate(historyQuerySchema, 'query'), async (req, res) => {
    const items = await store.listHistory(req.user.uid, req.valid.query);
    res.json({
      items: items.map((q) => ({
        queryId: String(q._id),
        question: q.question,
        status: q.status,
        code: q.code ?? null,
        latencyMs: q.latencyMs,
        createdAt: q.createdAt,
      })),
    });
  });

  router.get('/queries/:id', validate(idParamSchema, 'params'), async (req, res) => {
    const record = await store.getQuery(req.valid.params.id);
    if (!record) throw new AppError('NOT_FOUND');
    if (record.uid !== req.user.uid) throw new AppError('FORBIDDEN');
    res.json(toClient(record));
  });

  return router;
}
