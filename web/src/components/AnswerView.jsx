import { forwardRef, lazy, Suspense } from 'react';
import { formatMs } from '../lib/format.js';
import { AnswerCard } from './AnswerCard.jsx';
import { ExampleQuestions } from './ExampleQuestions.jsx';
import { ResultTable } from './ResultTable.jsx';
import { StatusBadge } from './StatusBadge.jsx';
import { TracePanel } from './TracePanel.jsx';

// Recharts is the heaviest dependency; load it only when there is a chart to draw.
const ResultChart = lazy(() => import('./ResultChart.jsx'));

const BLOCK_HELP = {
  OUT_OF_SCOPE: 'InsightPilot answers questions about the store’s orders, products, customers and website traffic.',
  UNSAFE_REQUEST: 'The request was stopped before any AI or database call.',
  UNSAFE_SQL: 'The generated SQL broke a safety rule, so it was never run.',
  COST_LIMIT: 'The query would have scanned too much data, so it was never run.',
};

/** Full result for one question. The heading receives focus when a new answer arrives. */
export const AnswerView = forwardRef(function AnswerView({ result, onExample }, headingRef) {
  const answered = result.status === 'answered' || result.status === 'cached';
  return (
    <article aria-labelledby="answer-heading" className="mt-8 space-y-5">
      <header className="flex flex-wrap items-center gap-3">
        <h2 id="answer-heading" ref={headingRef} tabIndex={-1} className="text-xl font-semibold text-slate-900">
          {result.question ?? 'Answer'}
        </h2>
        <StatusBadge status={result.status} />
        {result.cached && (
          <span className="text-sm text-slate-700">
            Served from cache in {formatMs(result.metrics.latencyMs)} — 0 AI calls, 0 bytes scanned
          </span>
        )}
      </header>

      {answered ? (
        <>
          <AnswerCard answer={result.answer} />
          {result.chart && result.chart.type !== 'table' && (
            <Suspense fallback={<p className="text-sm text-slate-700">Loading chart…</p>}>
              <ResultChart chart={result.chart} data={result.data} />
            </Suspense>
          )}
          <ResultTable data={result.data} caption={result.question} />
        </>
      ) : (
        <div
          role="alert"
          className={`rounded-xl border p-5 ${
            result.status === 'blocked' ? 'border-amber-300 bg-amber-50' : 'border-rose-300 bg-rose-50'
          }`}
        >
          <p className="font-semibold text-slate-900">
            {result.status === 'blocked' ? 'Request blocked' : 'Could not answer'}
            {result.code ? ` (${result.code})` : ''}
          </p>
          <p className="mt-1 text-slate-800">{result.message}</p>
          {BLOCK_HELP[result.code] && <p className="mt-1 text-sm text-slate-700">{BLOCK_HELP[result.code]}</p>}
          {result.code === 'OUT_OF_SCOPE' && onExample && (
            <ExampleQuestions onPick={onExample} label="Questions I can answer" />
          )}
        </div>
      )}

      <TracePanel result={result} />
    </article>
  );
});
