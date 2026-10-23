/** Shapes agent results into audit records and audit records into API responses. */

export const ROWS_STORED = 50;
export const ROWS_RETURNED = 200;

const STATUS_HTTP = { answered: 200, cached: 200, blocked: 422 };
const FAILURE_HTTP = { SQL_FAILED: 502, LLM_UNAVAILABLE: 503, TIMEOUT: 504 };

export function httpStatusFor(record) {
  return STATUS_HTTP[record.status] ?? FAILURE_HTTP[record.code] ?? 500;
}

export function toRecord(result, { requestId, uid, question, questionHash, latencyMs, model, promptVersion }) {
  const metrics = result.metrics ?? {};
  const data = result.data ?? { columns: [], rows: [], rowCount: 0 };
  return {
    requestId,
    uid,
    question,
    questionHash,
    status: result.status,
    code: result.code ?? null,
    message: result.message ?? null,
    sql: result.sql ?? null,
    bqJobId: result.jobId ?? null,
    bytesEstimate: metrics.bytesEstimate ?? null,
    bytesProcessed: metrics.bytesProcessed ?? 0,
    rowCount: data.rowCount ?? data.rows.length,
    columns: data.columns,
    rowsPreview: data.rows.slice(0, ROWS_STORED),
    facts: result.answer?.facts ?? [],
    assumptions: result.answer?.assumptions ?? [],
    insight: result.answer?.insight ?? null,
    insightSource: result.answer?.insightSource ?? null,
    chart: result.chart ?? null,
    trace: result.trace ?? [],
    attempts: metrics.attempts ?? 0,
    llm: {
      model: result.model ?? model,
      calls: metrics.llmCalls ?? 0,
      inputTokens: metrics.inputTokens ?? 0,
      outputTokens: metrics.outputTokens ?? 0,
    },
    agentLatencyMs: metrics.latencyMs ?? null,
    latencyMs,
    promptVersion: result.promptVersion ?? promptVersion,
  };
}

/** A cache hit is a new audit row that reuses the answer but costs nothing. */
export function toCachedRecord(original, { requestId, uid, question, latencyMs }) {
  return {
    ...stripMongoFields(original),
    requestId,
    uid,
    question,
    status: 'cached',
    bytesProcessed: 0,
    attempts: 0,
    llm: { ...original.llm, calls: 0, inputTokens: 0, outputTokens: 0 },
    trace: [{ step: 'cache', status: 'ok', ms: latencyMs, detail: `answer reused from ${original.requestId}` }],
    agentLatencyMs: 0,
    latencyMs,
    cachedFrom: original._id,
  };
}

export function toClient(record, rows) {
  const answered = record.status === 'answered' || record.status === 'cached';
  const shownRows = (rows ?? record.rowsPreview ?? []).slice(0, ROWS_RETURNED);
  return {
    queryId: record._id ? String(record._id) : null,
    question: record.question,
    status: record.status,
    cached: record.status === 'cached',
    code: record.code ?? null,
    message: record.message ?? null,
    answer: answered
      ? { insight: record.insight, facts: record.facts, assumptions: record.assumptions ?? [] }
      : null,
    data: answered
      ? {
          columns: record.columns ?? [],
          rows: shownRows,
          rowCount: record.rowCount ?? shownRows.length,
          truncated: (record.rowCount ?? 0) > shownRows.length,
        }
      : null,
    chart: answered ? record.chart : null,
    sql: record.sql ?? null,
    jobId: record.bqJobId ?? null,
    trace: record.trace ?? [],
    metrics: {
      latencyMs: record.latencyMs,
      bytesEstimate: record.bytesEstimate ?? null,
      bytesProcessed: record.bytesProcessed ?? 0,
      llmCalls: record.llm?.calls ?? 0,
      inputTokens: record.llm?.inputTokens ?? 0,
      outputTokens: record.llm?.outputTokens ?? 0,
      attempts: record.attempts ?? 0,
    },
    model: record.llm?.model ?? null,
    promptVersion: record.promptVersion ?? null,
    createdAt: record.createdAt ?? null,
  };
}

function stripMongoFields(doc) {
  const { _id, __v, createdAt, updatedAt, cachedFrom, ...rest } = doc;
  return rest;
}
