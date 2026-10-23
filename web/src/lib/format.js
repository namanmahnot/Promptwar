const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });

export function formatValue(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') return number.format(value);
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

export function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '—';
  if (bytes === 0) return '0 MB';
  if (bytes < 1e6) return `${number.format(bytes / 1e3)} KB`;
  if (bytes < 1e9) return `${number.format(bytes / 1e6)} MB`;
  return `${number.format(bytes / 1e9)} GB`;
}

export function formatMs(ms) {
  if (ms === null || ms === undefined) return '—';
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function formatPercent(ratio) {
  if (ratio === null || ratio === undefined) return '—';
  return `${(ratio * 100).toFixed(ratio === 1 || ratio === 0 ? 0 : 1)}%`;
}

export function formatDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function humanize(name) {
  return String(name).replaceAll('_', ' ');
}
