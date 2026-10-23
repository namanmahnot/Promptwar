import { useEffect, useState } from 'react';
import { formatBytes, formatDateTime, formatMs, formatPercent } from '../lib/format.js';
import { useApi } from '../lib/useApi.js';
import { useDocumentTitle } from '../lib/useDocumentTitle.js';

function Stat({ label, value, target }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <dt className="text-sm text-slate-700">{label}</dt>
      <dd className="mt-1 text-2xl font-bold text-slate-900 tabular-nums">{value}</dd>
      {target && <dd className="mt-0.5 text-xs text-slate-700">Target: {target}</dd>}
    </div>
  );
}

export function Metrics() {
  const api = useApi();
  const [evalRun, setEvalRun] = useState(undefined);
  const [error, setError] = useState(null);
  useDocumentTitle('Metrics');

  useEffect(() => {
    api.evalLatest().then((latest) => setEvalRun(latest.run), (err) => setError(err.message));
  }, [api]);

  return (
    <>
      <h1 className="text-2xl font-bold text-slate-900">Proof: accuracy, safety, speed and cost</h1>
      <p className="mt-1 text-slate-700">Measured on a golden set of 20 questions and 10 attack prompts, run against the live model and BigQuery.</p>
      {error && (
        <p role="alert" className="mt-4 text-rose-800">
          {error}
        </p>
      )}
      {evalRun === undefined && !error && (
        <p role="status" className="mt-4 text-slate-700">
          Loading…
        </p>
      )}

      <section aria-labelledby="eval-heading" className="mt-8">
        <h2 id="eval-heading" className="text-lg font-semibold text-slate-900">
          Latest evaluation run
        </h2>
        {evalRun === null && <p className="mt-2 text-slate-700">No evaluation has been run yet.</p>}
        {evalRun && (
          <>
            <p className="mt-1 text-sm text-slate-700">
              {formatDateTime(evalRun.startedAt)} · model {evalRun.model} · prompt {evalRun.promptVersion}
            </p>
            <dl className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Execution accuracy" value={formatPercent(evalRun.executionAccuracy)} target="≥ 80%" />
              <Stat label="Attacks blocked" value={formatPercent(evalRun.attackBlockRate)} target="100%" />
              <Stat label="Valid SQL rate" value={formatPercent(evalRun.validSqlRate)} target="≥ 95%" />
              <Stat label="Ungrounded numbers" value={evalRun.groundingViolations ?? 0} target="0" />
              <Stat label="Latency p50" value={formatMs(evalRun.p50Ms)} target="≤ 8 s" />
              <Stat label="Latency p95" value={formatMs(evalRun.p95Ms)} target="≤ 15 s" />
              <Stat label="Median bytes scanned" value={formatBytes(evalRun.medianBytes)} target="cap 1 GB" />
              <Stat label="Mean LLM calls" value={evalRun.meanLlmCalls} target="2 typical" />
            </dl>
            {evalRun.results?.length > 0 && (
              <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200 bg-white" tabIndex={0} role="region" aria-label="Golden question results">
                <table className="w-full text-sm">
                  <caption className="sr-only">Pass or fail for each golden question</caption>
                  <thead className="bg-slate-100">
                    <tr>
                      <th scope="col" className="px-3 py-2 text-left">ID</th>
                      <th scope="col" className="px-3 py-2 text-left">Question</th>
                      <th scope="col" className="px-3 py-2 text-left">Result</th>
                      <th scope="col" className="px-3 py-2 text-right">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalRun.results.map((r) => (
                      <tr key={r.qid} className="border-t border-slate-100 align-top">
                        <th scope="row" className="px-3 py-2 text-left font-mono font-medium">{r.qid}</th>
                        <td className="px-3 py-2">
                          {r.question}
                          {r.sql && (
                            <details className="mt-1">
                              <summary className="cursor-pointer text-indigo-800">SQL</summary>
                              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded bg-slate-900 p-2 text-xs text-slate-100">
                                <code>{r.sql}</code>
                              </pre>
                            </details>
                          )}
                        </td>
                        <td className={`px-3 py-2 font-semibold ${r.pass ? 'text-emerald-800' : 'text-rose-800'}`}>
                          {r.pass ? 'Pass' : `Fail${r.code ? ` (${r.code})` : ''}`}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatMs(r.ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
    </>
  );
}
