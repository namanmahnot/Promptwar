import { formatValue, humanize } from '../lib/format.js';

const NUMERIC = new Set(['INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC']);

export function ResultTable({ data, caption = 'Query result' }) {
  if (!data.columns.length) return null;
  return (
    <section aria-labelledby="table-heading" className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-5 pt-4">
        <h3 id="table-heading" className="text-sm font-semibold uppercase tracking-wide text-slate-600">
          Data
        </h3>
        <p className="text-sm text-slate-700">
          {data.truncated
            ? `Showing ${data.rows.length} of ${data.rowCount} rows`
            : `${data.rowCount} row${data.rowCount === 1 ? '' : 's'}`}
        </p>
      </div>
      {/* Scrollable region is focusable so keyboard users can scroll it. */}
      <div className="mt-3 max-h-96 overflow-auto" tabIndex={0} role="region" aria-label="Result rows, scrollable">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 bg-slate-100">
            <tr>
              {data.columns.map((column) => (
                <th
                  key={column.name}
                  scope="col"
                  className={`px-4 py-2 font-semibold text-slate-800 ${NUMERIC.has(column.type) ? 'text-right' : 'text-left'}`}
                >
                  {humanize(column.name)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, index) => (
              // Rows have no stable id; index is fine because the list never reorders.
              <tr key={index} className="border-t border-slate-100 odd:bg-white even:bg-slate-50">
                {data.columns.map((column) => (
                  <td
                    key={column.name}
                    className={`px-4 py-2 text-slate-900 ${NUMERIC.has(column.type) ? 'text-right tabular-nums' : ''}`}
                  >
                    {formatValue(row[column.name])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
