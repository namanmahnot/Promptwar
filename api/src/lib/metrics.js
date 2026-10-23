/** Live aggregates over recent audit rows, for the Metrics page. Pure function, store-agnostic. */

export function percentile(values, pct) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil((pct / 100) * sorted.length) - 1)];
}

export function summarizeLive(records) {
  const byStatus = { answered: 0, cached: 0, blocked: 0, failed: 0 };
  for (const record of records) byStatus[record.status] = (byStatus[record.status] ?? 0) + 1;

  const answered = records.filter((r) => r.status === 'answered');
  const cached = records.filter((r) => r.status === 'cached');
  const served = answered.length + cached.length;
  const llmCalls = records.map((r) => r.llm?.calls ?? 0);

  return {
    count: records.length,
    byStatus,
    cacheHitRate: served ? cached.length / served : null,
    p50LatencyMs: percentile(answered.map((r) => r.latencyMs), 50),
    p95LatencyMs: percentile(answered.map((r) => r.latencyMs), 95),
    p50CachedLatencyMs: percentile(cached.map((r) => r.latencyMs), 50),
    medianBytesProcessed: percentile(answered.map((r) => r.bytesProcessed ?? 0), 50),
    meanLlmCalls: records.length ? llmCalls.reduce((a, b) => a + b, 0) / records.length : null,
  };
}
