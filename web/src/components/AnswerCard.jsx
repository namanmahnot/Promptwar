import { formatValue } from '../lib/format.js';

export function AnswerCard({ answer }) {
  const facts = answer.facts.filter((fact) => fact.label !== 'Rows returned');
  return (
    <section aria-labelledby="insight-heading" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 id="insight-heading" className="text-sm font-semibold uppercase tracking-wide text-slate-600">
        Insight
      </h3>
      <p className="mt-2 text-lg leading-relaxed text-slate-900">{answer.insight}</p>

      {facts.length > 0 && (
        <>
          <h3 className="mt-5 text-sm font-semibold uppercase tracking-wide text-slate-600">Key numbers</h3>
          <dl className="mt-2 grid gap-3 sm:grid-cols-2">
            {facts.map((fact) => (
              <div key={fact.label} className="rounded-lg bg-slate-50 p-3">
                <dt className="text-sm text-slate-700">{fact.label}</dt>
                <dd className="mt-0.5 text-base font-semibold text-slate-900 tabular-nums">{formatValue(fact.value)}</dd>
              </div>
            ))}
          </dl>
        </>
      )}

      {answer.assumptions?.length > 0 && (
        <>
          <h3 className="mt-5 text-sm font-semibold uppercase tracking-wide text-slate-600">Assumptions</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-800">
            {answer.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </>
      )}
      <p className="mt-4 text-xs text-slate-600">
        Every number above was computed from the BigQuery result, not written by the AI.
      </p>
    </section>
  );
}
