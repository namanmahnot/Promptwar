import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AnswerView } from '../components/AnswerView.jsx';
import { useApi } from '../lib/useApi.js';
import { useDocumentTitle } from '../lib/useDocumentTitle.js';

export function QueryDetail() {
  const { id } = useParams();
  const api = useApi();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  useDocumentTitle(result?.question ?? 'Saved answer');

  useEffect(() => {
    api.query(id).then(setResult, (err) => setError(err.message));
  }, [api, id]);

  return (
    <>
      <p>
        <Link to="/history" className="text-sm font-medium text-indigo-800 underline">
          ← Back to history
        </Link>
      </p>
      <h1 className="mt-2 text-2xl font-bold text-slate-900">Saved answer</h1>
      {error && (
        <p role="alert" className="mt-4 text-rose-800">
          {error}
        </p>
      )}
      {!result && !error && (
        <p role="status" className="mt-4 text-slate-700">
          Loading…
        </p>
      )}
      {result && <AnswerView result={result} />}
    </>
  );
}
