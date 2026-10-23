// Cells starting with these characters are executed as formulas by spreadsheet apps.
const FORMULA_START = /^[=+\-@\t\r]/;

function escapeCell(value) {
  if (value === null || value === undefined) return '';
  let text = String(value);
  if (typeof value === 'string' && FORMULA_START.test(text)) text = `'${text}`;
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/** RFC 4180 CSV with spreadsheet formula-injection protection. */
export function toCsv(columns, rows) {
  const header = columns.map((c) => escapeCell(c.name)).join(',');
  const body = rows.map((row) => columns.map((c) => escapeCell(row[c.name])).join(','));
  return [header, ...body].join('\r\n');
}

export function downloadCsv(filename, columns, rows) {
  const blob = new Blob([toCsv(columns, rows)], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function csvFilename(question) {
  const slug = (question ?? 'result').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60);
  return `${slug || 'result'}.csv`;
}
