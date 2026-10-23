import { useEffect, useRef, useState } from 'react';
import { AnswerView } from '../components/AnswerView.jsx';
import { ExampleQuestions } from '../components/ExampleQuestions.jsx';
import { ProgressSteps } from '../components/ProgressSteps.jsx';
import { useApi } from '../lib/useApi.js';
import { useDocumentTitle } from '../lib/useDocumentTitle.js';

const MIN_CHARS = 3;
const MAX_CHARS = 500;

export function Ask() {
  const api = useApi();
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const answerHeading = useRef(null);
  const controller = useRef(null);
  useDocumentTitle('Ask');

  useEffect(() => () => controller.current?.abort(), []);

  useEffect(() => {
    if (result) answerHeading.current?.focus();
  }, [result]);

  async function submit(text) {
    const trimmed = text.trim();
    if (trimmed.length < MIN_CHARS) {
      setError(`Please enter at least ${MIN_CHARS} characters.`);
      return;
    }
    controller.current?.abort();
    controller.current = new AbortController();
    setQuestion(trimmed);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.ask(trimmed, controller.current.signal));
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const remaining = MAX_CHARS - question.length;

  return (
    <>
      <h1 className="text-2xl font-bold text-slate-900">Ask a question about the store</h1>
      <p className="mt-1 text-slate-700">Orders, revenue, products, customers by region and website traffic.</p>

      <form
        className="mt-6"
        onSubmit={(event) => {
          event.preventDefault();
          submit(question);
        }}
        aria-busy={loading}
      >
        <label htmlFor="question" className="block font-medium text-slate-900">
          Your question
        </label>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-start">
          <textarea
            id="question"
            name="question"
            rows={2}
            maxLength={MAX_CHARS}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submit(question);
              }
            }}
            aria-describedby="question-hint"
            aria-invalid={Boolean(error) || undefined}
            placeholder="e.g. Top 5 product categories by revenue in the last 90 days"
            className="w-full resize-y rounded-lg border border-slate-400 bg-white px-3 py-2 text-base text-slate-900 placeholder:text-slate-500"
          />
          <button
            type="submit"
            disabled={loading}
            className="min-h-11 shrink-0 rounded-lg bg-indigo-700 px-5 font-semibold text-white hover:bg-indigo-800 disabled:cursor-wait disabled:bg-indigo-400"
          >
            {loading ? 'Analysing…' : 'Ask'}
          </button>
        </div>
        <p id="question-hint" className="mt-1 text-sm text-slate-700">
          Press Enter to ask, Shift+Enter for a new line. {remaining} characters left.
        </p>
      </form>

      {!result && !loading && <ExampleQuestions onPick={submit} disabled={loading} />}

      {error && (
        <p role="alert" className="mt-6 rounded-lg border border-rose-300 bg-rose-50 p-4 font-medium text-rose-900">
          {error}
        </p>
      )}
      {loading && <ProgressSteps />}
      {result && <AnswerView ref={answerHeading} result={result} onExample={submit} />}
    </>
  );
}
