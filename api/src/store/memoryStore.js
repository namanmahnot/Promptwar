import { randomBytes } from 'node:crypto';

/** In-memory store with the same interface as the Mongo store. Used by tests and by local runs without MONGO_URI. */
export function createMemoryStore() {
  const users = new Map();
  const queries = [];
  const cache = new Map();
  const evalRuns = [];
  const newId = () => randomBytes(12).toString('hex');
  const copy = (value) => (value ? structuredClone(value) : null);

  return {
    users,
    queries,
    async upsertUser({ uid, email, name }) {
      users.set(uid, { _id: uid, email, displayName: name, lastSeenAt: new Date() });
    },
    async findCached(key) {
      const entry = cache.get(key);
      if (!entry || entry.expiresAt <= Date.now()) return null;
      return copy(queries.find((q) => q._id === entry.queryId));
    },
    async saveCache(key, queryId, ttlMs) {
      cache.set(key, { queryId: String(queryId), expiresAt: Date.now() + ttlMs });
    },
    async saveQuery(record) {
      if (queries.some((q) => q.requestId === record.requestId)) throw new Error('duplicate requestId');
      const doc = { ...structuredClone(record), _id: newId(), createdAt: new Date() };
      queries.push(doc);
      return copy(doc);
    },
    async getQuery(id) {
      return copy(queries.find((q) => q._id === id));
    },
    async listHistory(uid, { limit, before }) {
      return queries
        .filter((q) => q.uid === uid && (!before || q.createdAt < new Date(before)))
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, limit)
        .map(copy);
    },
    async recentQueries(n) {
      return [...queries].sort((a, b) => b.createdAt - a.createdAt).slice(0, n).map(copy);
    },
    async latestEvalRun() {
      return copy(evalRuns.at(-1));
    },
    async saveEvalRun(summary) {
      const doc = { ...structuredClone(summary), _id: newId() };
      evalRuns.push(doc);
      return copy(doc);
    },
    async close() {},
  };
}
