import mongoose from 'mongoose';

const { Schema } = mongoose;

const userSchema = new Schema(
  {
    _id: { type: String, required: true }, // Firebase uid
    email: { type: String, default: null },
    displayName: { type: String, default: null },
    role: { type: String, enum: ['user', 'admin'], default: 'user' },
    lastSeenAt: { type: Date, default: Date.now },
  },
  { timestamps: { createdAt: true, updatedAt: false }, strict: 'throw' },
);

/** One row per request: the audit trail (docs/02 "Data model"). */
const querySchema = new Schema(
  {
    requestId: { type: String, required: true },
    uid: { type: String, required: true },
    question: { type: String, required: true, maxlength: 500 },
    questionHash: { type: String, required: true },
    status: { type: String, enum: ['answered', 'cached', 'blocked', 'failed'], required: true },
    code: { type: String, default: null },
    message: { type: String, default: null },
    sql: { type: String, default: null },
    bqJobId: { type: String, default: null },
    bytesEstimate: { type: Number, default: null },
    bytesProcessed: { type: Number, default: 0 },
    rowCount: { type: Number, default: 0 },
    columns: { type: [{ _id: false, name: String, type: { type: String } }], default: [] },
    rowsPreview: { type: [Schema.Types.Mixed], default: [] },
    facts: { type: [{ _id: false, label: String, value: Schema.Types.Mixed }], default: [] },
    assumptions: { type: [String], default: [] },
    insight: { type: String, default: null },
    insightSource: { type: String, default: null },
    chart: { type: Schema.Types.Mixed, default: null },
    trace: { type: [Schema.Types.Mixed], default: [] },
    attempts: { type: Number, default: 0 },
    llm: {
      model: String,
      calls: { type: Number, default: 0 },
      inputTokens: { type: Number, default: 0 },
      outputTokens: { type: Number, default: 0 },
    },
    agentLatencyMs: { type: Number, default: null },
    latencyMs: { type: Number, required: true },
    promptVersion: { type: String, default: null },
    cachedFrom: { type: Schema.Types.ObjectId, default: null },
  },
  { timestamps: { createdAt: true, updatedAt: false } },
);
querySchema.index({ uid: 1, createdAt: -1 });
querySchema.index({ questionHash: 1 });
querySchema.index({ requestId: 1 }, { unique: true });
querySchema.index({ createdAt: -1 });

const cacheSchema = new Schema({
  _id: { type: String, required: true }, // sha256(normalized question + model + prompt version)
  queryId: { type: Schema.Types.ObjectId, required: true },
  expiresAt: { type: Date, required: true },
});
cacheSchema.index({ expiresAt: 1 }, { expireAfterSeconds: 0 });

const evalRunSchema = new Schema(
  {
    startedAt: { type: Date, required: true },
    finishedAt: Date,
    model: String,
    modelLite: String,
    promptVersion: String,
    n: Number,
    executionAccuracy: Number,
    validSqlRate: Number,
    selfCorrectionRate: Number,
    attackBlockRate: Number,
    groundingViolations: Number,
    p50Ms: Number,
    p95Ms: Number,
    medianBytes: Number,
    meanLlmCalls: Number,
    meanTokens: Number,
    results: [Schema.Types.Mixed],
    attacks: [Schema.Types.Mixed],
  },
  { collection: 'eval_runs' },
);
evalRunSchema.index({ startedAt: -1 });

export const User = mongoose.model('User', userSchema);
export const Query = mongoose.model('Query', querySchema);
export const Cache = mongoose.model('Cache', cacheSchema, 'cache');
export const EvalRun = mongoose.model('EvalRun', evalRunSchema);
