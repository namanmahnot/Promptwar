import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { StatusBadge } from '../components/StatusBadge.jsx';
import { formatDateTime, formatMs } from '../lib/format.js';
import { useApi } from '../lib/useApi.js';
import { useDocumentTitle } from '../lib/useDocumentTitle.js';

export function History() {
  const api = useApi();
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  useDocumentTitle('History');

  useEffect(() => {
    api.history().then((body) => setItems(body.items), (err) => setError(err.message));
  }, [api]);

  return (
    <>
      <h1 className="text-2xl font-bold text-slate-900">Your recent questions</h1>
      {error && (
        <p role="alert" className="mt-4 text-rose-800">
          {error}
        </p>
      )}
      {!items && !error && (
        <p role="status" className="mt-4 text-slate-700">
          Loading…
        </p>
      )}
      {items?.length === 0 && (
        <p className="mt-4 text-slate-700">
          No questions yet. <Link to="/" className="font-medium text-indigo-800 underline">Ask your first one</Link>.
        </p>
      )}
      {items?.length > 0 && (
        <ul className="mt-6 divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
          {items.map((item) => (
            <li key={item.queryId}>
              <Link
                to={`/history/${item.queryId}`}
                className="flex min-h-11 flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-slate-50"
              >
                <span className="font-medium text-slate-900">{item.question}</span>
                <span className="flex items-center gap-3 text-sm text-slate-700">
                  <StatusBadge status={item.status} />
                  <span>{formatMs(item.latencyMs)}</span>
                  <time dateTime={item.createdAt}>{formatDateTime(item.createdAt)}</time>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
