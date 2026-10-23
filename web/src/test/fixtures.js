export const answered = {
  queryId: 'q1',
  question: 'Top categories by revenue',
  status: 'answered',
  cached: false,
  code: null,
  message: null,
  answer: {
    insight: 'Outerwear & Coats led revenue with 1,500.5.',
    facts: [
      { label: 'Rows returned', value: 2 },
      { label: 'Highest category', value: 'Outerwear & Coats' },
      { label: 'Highest revenue', value: 1500.5 },
    ],
    assumptions: ['Counts completed items only.'],
  },
  data: {
    columns: [
      { name: 'category', type: 'STRING' },
      { name: 'revenue', type: 'FLOAT64' },
    ],
    rows: [
      { category: 'Outerwear & Coats', revenue: 1500.5 },
      { category: 'Jeans', revenue: 1200 },
    ],
    rowCount: 2,
    truncated: false,
  },
  chart: { type: 'bar', x: 'category', y: 'revenue' },
  sql: 'SELECT category, revenue FROM t LIMIT 1000',
  jobId: 'job_123',
  trace: [
    { step: 'prefilter', status: 'ok', ms: 1, detail: 'no unsafe patterns' },
    { step: 'write_sql', status: 'ok', ms: 2100, detail: 'attempt 1' },
    { step: 'execute', status: 'ok', ms: 900, detail: '2 rows' },
  ],
  metrics: { latencyMs: 4200, bytesProcessed: 2_500_000, llmCalls: 2, attempts: 1, inputTokens: 900, outputTokens: 80 },
  model: 'gemini-3.5-flash',
  promptVersion: 'v1',
};

export const blocked = {
  ...answered,
  status: 'blocked',
  code: 'UNSAFE_SQL',
  message: 'Query references a restricted column (users.email).',
  answer: null,
  data: null,
  chart: null,
  jobId: null,
};
