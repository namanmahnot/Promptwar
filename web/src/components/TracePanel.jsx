import { useState } from 'react';
import { formatBytes, formatMs } from '../lib/format.js';

const STEP_LABELS = {
  prefilter: 'Safety pre-filter',
  write_sql: 'Write SQL (Gemini)',
  validate_sql: 'Validate SQL',
  dry_run: 'Dry run (cost check)',
  execute: 'Run on BigQuery',
  compute_facts: 'Compute facts',
  chart: 'Choose chart',
  explain: 'Explain (Gemini Flash-Lite)',
  cache: 'Answer cache',
};

const STATUS_TEXT = { ok: 'OK', retry: 'Retried', blocked: 'Blocked', error: 'Error' };

/** "Why can I trust this?" — every step, the SQL, bytes scanned and the BigQuery job id. */
export function TracePanel({ result }) {
  const [copied, setCopied] = useState(false);
  const { metrics } = result;

  async function copySql() {
    try {
      await navigator.clipboard.writeText(result.sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <details className="group rounded-xl border border-slate-200 bg-white shadow-sm">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 px-5 py-3 font-semibold text-slate-900">
        <span>How this answer was produced</span>
        <span aria-hidden="true" className="text-slate-500 transition group-open:rotate-180">
          ▾
        </span>
      </summary>
      <div className="border-t border-slate-100 px-5 pb-5 pt-4">
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          {[
            ['Total time', formatMs(metrics.latencyMs)],
            ['Bytes scanned', formatBytes(metrics.bytesProcessed)],
            ['LLM calls', metrics.llmCalls],
            ['SQL attempts', metrics.attempts],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg bg-slate-50 p-3">
              <dt className="text-slate-700">{label}</dt>
              <dd className="font-semibold text-slate-900 tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>

        <h3 className="mt-5 text-sm font-semibold text-slate-800">Steps</h3>
        <ol className="mt-2 divide-y divide-slate-100 text-sm">
          {result.trace.map((step, index) => (
            <li key={`${step.step}-${index}`} className="grid grid-cols-[1fr_auto] gap-x-3 py-2">
              <span className="font-medium text-slate-900">
                {STEP_LABELS[step.step] ?? step.step}{' '}
                <span className={step.status === 'ok' ? 'text-emerald-800' : 'text-amber-800'}>
                  — {STATUS_TEXT[step.status] ?? step.status}
                </span>
              </span>
              <span className="text-right tabular-nums text-slate-700">{formatMs(step.ms)}</span>
              {step.detail && <span className="col-span-2 break-words text-slate-700">{step.detail}</span>}
            </li>
          ))}
        </ol>

        {result.sql && (
          <>
            <div className="mt-5 flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-slate-800">SQL</h3>
              <button
                type="button"
                onClick={copySql}
                className="min-h-11 rounded-md border border-slate-300 px-3 text-sm font-medium text-slate-800 hover:bg-slate-50"
              >
                Copy SQL
              </button>
            </div>
            <span role="status" className="sr-only">
              {copied ? 'SQL copied to clipboard' : ''}
            </span>
            <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">
              <code>{result.sql}</code>
            </pre>
          </>
        )}

        <p className="mt-4 text-xs text-slate-700">
          {result.jobId ? <>BigQuery job: <code className="break-all">{result.jobId}</code> · </> : null}
          Model: {result.model ?? '—'} · Prompt {result.promptVersion ?? '—'}
        </p>
      </div>
    </details>
  );
}
