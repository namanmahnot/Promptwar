export const EXAMPLE_QUESTIONS = [
  'Top 5 product categories by revenue in the last 90 days',
  'Monthly number of orders over the last 12 months',
  'Which traffic source brings the most users?',
  'Return rate by product department',
];

export function ExampleQuestions({ onPick, disabled = false, label = 'Try an example' }) {
  return (
    <section aria-labelledby="examples-heading" className="mt-4">
      <h2 id="examples-heading" className="text-sm font-medium text-slate-700">
        {label}
      </h2>
      <ul className="mt-2 flex flex-wrap gap-2">
        {EXAMPLE_QUESTIONS.map((question) => (
          <li key={question}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(question)}
              className="min-h-11 rounded-full border border-slate-300 bg-white px-3 py-2 text-left text-sm text-slate-800 hover:border-indigo-500 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {question}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
