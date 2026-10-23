import { useEffect, useState } from 'react';

/** Typical step timings (docs/04 latency budget) — a perceived-speed aid while the agent works. */
export const STEPS = [
  { label: 'Checking the question', at: 0 },
  { label: 'Writing SQL with Gemini', at: 300 },
  { label: 'Validating the SQL', at: 2800 },
  { label: 'Estimating cost with a dry run', at: 3100 },
  { label: 'Running on BigQuery', at: 3600 },
  { label: 'Computing facts and explaining', at: 5200 },
];

const SLOW_AFTER_MS = 15_000;

export function ProgressSteps() {
  const [active, setActive] = useState(0);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timers = STEPS.slice(1).map((step, index) => setTimeout(() => setActive(index + 1), step.at));
    timers.push(setTimeout(() => setSlow(true), SLOW_AFTER_MS));
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p role="status" aria-live="polite" className="font-medium text-slate-900">
        {STEPS[active].label}…
      </p>
      <ol className="mt-3 space-y-1.5" aria-label="Analysis steps">
        {STEPS.map((step, index) => {
          const state = index < active ? 'done' : index === active ? 'current' : 'pending';
          return (
            <li
              key={step.label}
              aria-current={state === 'current' ? 'step' : undefined}
              className={`flex items-center gap-2 text-sm ${state === 'pending' ? 'text-slate-500' : 'text-slate-900'}`}
            >
              <span
                aria-hidden="true"
                className={`inline-block size-2.5 rounded-full ${
                  state === 'done' ? 'bg-emerald-600' : state === 'current' ? 'animate-pulse bg-indigo-600' : 'bg-slate-300'
                }`}
              />
              {step.label}
              <span className="sr-only">{state === 'done' ? ' (done)' : state === 'current' ? ' (in progress)' : ''}</span>
            </li>
          );
        })}
      </ol>
      {slow && (
        <p role="status" className="mt-3 text-sm text-slate-700">
          Taking longer than usual — the server may be waking up from sleep (free hosting). This can take up to a minute.
        </p>
      )}
    </div>
  );
}
