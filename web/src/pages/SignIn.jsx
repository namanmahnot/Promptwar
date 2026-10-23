import { useAuth } from '../lib/auth.jsx';
import { useDocumentTitle } from '../lib/useDocumentTitle.js';

const POINTS = [
  ['Plain English in, verified numbers out', 'Every number is computed from the query result, never invented by the AI.'],
  ['Safe by construction', 'Read-only SQL, no personal data, and a 1 GB scan cap enforced in code.'],
  ['Show your work', 'See the SQL, each step, bytes scanned and the BigQuery job behind every answer.'],
];

export function SignIn() {
  const { signIn, error, configured } = useAuth();
  useDocumentTitle('Sign in');

  return (
    <main id="main" className="mx-auto flex min-h-dvh max-w-3xl flex-col justify-center px-4 py-12">
      <h1 className="text-4xl font-bold tracking-tight text-slate-900">InsightPilot</h1>
      <p className="mt-3 text-lg text-slate-700">
        Ask a business question about the store and get an answer you can verify, in seconds.
      </p>
      <ul className="mt-8 space-y-4">
        {POINTS.map(([title, body]) => (
          <li key={title} className="rounded-xl border border-slate-200 bg-white p-4">
            <p className="font-semibold text-slate-900">{title}</p>
            <p className="mt-1 text-slate-700">{body}</p>
          </li>
        ))}
      </ul>
      <div className="mt-8">
        <button
          type="button"
          onClick={signIn}
          disabled={!configured}
          className="min-h-12 rounded-lg bg-indigo-700 px-6 text-base font-semibold text-white hover:bg-indigo-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          Sign in with Google
        </button>
        {!configured && (
          <p className="mt-3 text-sm text-slate-700">
            Sign-in is not configured. Set the <code>VITE_FIREBASE_*</code> variables (see README).
          </p>
        )}
        {error && (
          <p role="alert" className="mt-3 text-sm font-medium text-rose-800">
            {error}
          </p>
        )}
      </div>
    </main>
  );
}
