import { Router } from 'express';
import { summarizeLive } from '../lib/metrics.js';
import { requireAdmin } from '../middleware/auth.js';

const LIVE_WINDOW = 100;

export function metricsRouter({ store, agent, logger }) {
  const router = Router();

  router.get('/metrics/eval/latest', async (req, res) => {
    const run = await store.latestEvalRun();
    res.json({ run: run ? { ...run, _id: String(run._id) } : null });
  });

  router.get('/metrics/live', async (req, res) => {
    const records = await store.recentQueries(LIVE_WINDOW);
    res.json(summarizeLive(records));
  });

  router.post('/admin/eval/run', requireAdmin, async (req, res) => {
    logger.info('eval run started', { requestId: req.id, uid: req.user.uid });
    const summary = await agent.runEval(req.id);
    const saved = await store.saveEvalRun(summary);
    res.status(201).json({ run: { ...saved, _id: String(saved._id) } });
  });

  return router;
}
