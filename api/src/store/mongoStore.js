import mongoose from 'mongoose';
import { Cache, EvalRun, Query, User } from '../models/index.js';

const HISTORY_FIELDS = 'question status code createdAt latencyMs';
const LIVE_FIELDS = 'status latencyMs bytesProcessed llm.calls';

/** MongoDB-backed store. Routes depend only on this interface, so tests can swap in memory. */
export async function createMongoStore(uri) {
  mongoose.set('strictQuery', true);
  mongoose.set('sanitizeFilter', true); // strips $-operators from any filter built from input
  await mongoose.connect(uri, { serverSelectionTimeoutMS: 5000, socketTimeoutMS: 5000, dbName: 'insightpilot' });

  return {
    async upsertUser({ uid, email, name }) {
      await User.updateOne(
        { _id: uid },
        { $set: { email, displayName: name, lastSeenAt: new Date() }, $setOnInsert: { role: 'user' } },
        { upsert: true },
      );
    },

    async findCached(key) {
      // Operators we write ourselves are marked trusted; sanitizeFilter neutralises everything else.
      const entry = await Cache.findOne({ _id: key, expiresAt: mongoose.trusted({ $gt: new Date() }) }).lean();
      return entry ? Query.findById(entry.queryId).lean() : null;
    },

    async saveCache(key, queryId, ttlMs) {
      await Cache.updateOne(
        { _id: key },
        { $set: { queryId, expiresAt: new Date(Date.now() + ttlMs) } },
        { upsert: true },
      );
    },

    async saveQuery(record) {
      const doc = await Query.create(record);
      return doc.toObject();
    },

    getQuery: (id) => Query.findById(id).lean(),

    listHistory(uid, { limit, before }) {
      const filter = { uid, ...(before ? { createdAt: mongoose.trusted({ $lt: new Date(before) }) } : {}) };
      return Query.find(filter).sort({ createdAt: -1 }).limit(limit).select(HISTORY_FIELDS).lean();
    },

    recentQueries: (n) => Query.find().sort({ createdAt: -1 }).limit(n).select(LIVE_FIELDS).lean(),

    latestEvalRun: () => EvalRun.findOne().sort({ startedAt: -1 }).lean(),

    async saveEvalRun(summary) {
      const doc = await EvalRun.create(summary);
      return doc.toObject();
    },

    close: () => mongoose.disconnect(),
  };
}
