import { randomUUID } from 'node:crypto';
import express from 'express';
import helmet from 'helmet';
import { authenticate } from './middleware/auth.js';
import { cors } from './middleware/cors.js';
import { errorHandler, notFound } from './middleware/errors.js';
import { ipLimiter } from './middleware/rateLimit.js';
import { askRouter } from './routes/ask.js';
import { historyRouter } from './routes/history.js';
import { metricsRouter } from './routes/metrics.js';

/**
 * Builds the gateway. Every collaborator is injected so tests run without Firebase,
 * MongoDB or the agent. Middleware order follows docs/03 "Defense layers" 1–4.
 */
export function createApp({ config, verifyToken, agent, store, logger }) {
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', 1); // Cloud Run terminates TLS in front of us

  app.use((req, res, next) => {
    req.id = randomUUID();
    res.set('X-Request-Id', req.id);
    const started = performance.now();
    res.on('finish', () => {
      logger.info('request', {
        requestId: req.id,
        uid: req.user?.uid,
        method: req.method,
        path: req.path,
        status: res.statusCode,
        ms: Math.round(performance.now() - started),
      });
    });
    next();
  });

  app.use(helmet());
  app.use(cors(config.corsOrigins));
  app.use(ipLimiter());
  app.use(express.json({ limit: '10kb' }));

  app.get('/healthz', (req, res) => res.json({ ok: true }));

  const deps = { agent, store, config, logger };
  app.use('/api', authenticate({ verifyToken }));
  app.use('/api', askRouter(deps));
  app.use('/api', historyRouter(deps));
  app.use('/api', metricsRouter(deps));

  app.use(notFound);
  app.use(errorHandler(logger));
  return app;
}
