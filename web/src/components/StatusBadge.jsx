const STYLES = {
  answered: 'bg-emerald-100 text-emerald-900 ring-emerald-700/30',
  cached: 'bg-sky-100 text-sky-900 ring-sky-700/30',
  blocked: 'bg-amber-100 text-amber-900 ring-amber-700/30',
  failed: 'bg-rose-100 text-rose-900 ring-rose-700/30',
};

const LABELS = { answered: 'Answered', cached: 'Cached', blocked: 'Blocked', failed: 'Failed' };

/** Status is always conveyed in text, never by colour alone. */
export function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${
        STYLES[status] ?? 'bg-slate-100 text-slate-800 ring-slate-600/30'
      }`}
    >
      {LABELS[status] ?? status}
    </span>
  );
}
