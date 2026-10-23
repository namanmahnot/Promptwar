import { z } from 'zod';

const booleanString = z
  .enum(['true', 'false'])
  .default('false')
  .transform((value) => value === 'true');

const envSchema = z
  .object({
    NODE_ENV: z.enum(['development', 'production', 'test']).default('production'),
    PORT: z.coerce.number().int().positive().default(8080),
    MONGO_URI: z.string().min(1).optional(),
    AGENT_URL: z.url(),
    INTERNAL_API_KEY: z.string().min(16).optional(),
    CORS_ORIGINS: z.string().default(''),
    FIREBASE_PROJECT_ID: z.string().optional(),
    GEMINI_MODEL_SQL: z.string().default('gemini-3.5-flash'),
    PROMPT_VERSION: z.string().default('v1'),
    CACHE_TTL_HOURS: z.coerce.number().positive().default(6),
    AUTH_DEV_BYPASS: booleanString,
  })
  .refine((env) => !env.AUTH_DEV_BYPASS || env.NODE_ENV === 'development', {
    message: 'AUTH_DEV_BYPASS is only allowed when NODE_ENV=development',
    path: ['AUTH_DEV_BYPASS'],
  });

export function loadConfig(env = process.env) {
  const parsed = envSchema.safeParse(env);
  if (!parsed.success) {
    const issues = parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ');
    throw new Error(`Invalid configuration: ${issues}`);
  }
  const e = parsed.data;
  return {
    env: e.NODE_ENV,
    port: e.PORT,
    mongoUri: e.MONGO_URI,
    agentUrl: e.AGENT_URL.replace(/\/$/, ''),
    internalApiKey: e.INTERNAL_API_KEY,
    // Cloud Run IAM: sign agent calls with a Google ID token unless the agent is local
    // (the single-container deployment reaches it on 127.0.0.1).
    useAgentIdToken: e.AGENT_URL.startsWith('https://'),
    corsOrigins: e.CORS_ORIGINS.split(',').map((o) => o.trim()).filter(Boolean),
    firebaseProjectId: e.FIREBASE_PROJECT_ID,
    modelSql: e.GEMINI_MODEL_SQL,
    promptVersion: e.PROMPT_VERSION,
    cacheTtlMs: e.CACHE_TTL_HOURS * 60 * 60 * 1000,
    authDevBypass: e.AUTH_DEV_BYPASS,
  };
}
