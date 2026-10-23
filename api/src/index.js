import { createApp } from './app.js';
import { loadConfig } from './config.js';
import { createAgentClient } from './lib/agentClient.js';
import { createLogger } from './lib/logger.js';
import { createTokenVerifier } from './middleware/auth.js';
import { createMemoryStore } from './store/memoryStore.js';
import { createMongoStore } from './store/mongoStore.js';

const logger = createLogger();

async function main() {
  const config = loadConfig();

  let store;
  if (config.mongoUri) {
    store = await createMongoStore(config.mongoUri);
  } else if (config.env === 'development') {
    logger.warn('MONGO_URI not set; using in-memory store (data is lost on restart)');
    store = createMemoryStore();
  } else {
    throw new Error('MONGO_URI is required outside development');
  }

  const app = createApp({
    config,
    verifyToken: await createTokenVerifier(config),
    agent: createAgentClient(config),
    store,
    logger,
  });

  const server = app.listen(config.port, () => logger.info('gateway listening', { port: config.port }));

  const shutdown = (signal) => {
    logger.info('shutting down', { signal });
    server.close(() => store.close().finally(() => process.exit(0)));
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

main().catch((err) => {
  logger.error('startup failed', { error: err.message });
  process.exit(1);
});
