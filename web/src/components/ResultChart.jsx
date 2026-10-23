import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatValue, humanize } from '../lib/format.js';

const ACCENT = '#4338ca'; // indigo-700: 4.5:1+ against white

/**
 * Renders exactly the chart spec the agent chose by rule. The figure carries a text summary
 * for screen readers; the full data is always available in the table below it.
 */
export default function ResultChart({ chart, data }) {
  if (!chart || chart.type === 'table') return null;
  const { x, y } = chart;
  const rows = data.rows.map((row) => ({ ...row, [x]: formatValue(row[x]) }));
  const values = data.rows.map((row) => row[y]).filter((v) => typeof v === 'number');
  const summary = `${chart.type === 'line' ? 'Line' : 'Bar'} chart of ${humanize(y)} by ${humanize(x)}, ${
    rows.length
  } points, ranging from ${formatValue(Math.min(...values))} to ${formatValue(Math.max(...values))}. Full data in the table below.`;

  const axisProps = { stroke: '#334155', tick: { fill: '#334155', fontSize: 12 } };
  const ChartType = chart.type === 'line' ? LineChart : BarChart;

  return (
    <figure className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <figcaption className="text-sm font-semibold uppercase tracking-wide text-slate-600">
        {humanize(y)} by {humanize(x)}
      </figcaption>
      <div role="img" aria-label={summary} className="mt-3 h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ChartType data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey={x} {...axisProps} interval="preserveStartEnd" />
            <YAxis {...axisProps} tickFormatter={formatValue} width={80} />
            <Tooltip formatter={(value) => formatValue(value)} />
            {chart.type === 'line' ? (
              <Line type="monotone" dataKey={y} stroke={ACCENT} strokeWidth={2} dot={rows.length <= 40} />
            ) : (
              <Bar dataKey={y} fill={ACCENT} radius={[4, 4, 0, 0]} />
            )}
          </ChartType>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
