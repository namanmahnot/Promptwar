/** One JSON line per event on stdout; Cloud Logging parses `severity`. Secrets are redacted by key name. */
const REDACT = /(key|token|secret|authorization|password|cookie)/i;

function redact(fields) {
  return Object.fromEntries(
    Object.entries(fields).map(([key, value]) => [key, REDACT.test(key) ? '[redacted]' : value]),
  );
}

export function createLogger({ write = (line) => process.stdout.write(`${line}\n`), silent = false } = {}) {
  const log = (severity) => (message, fields = {}) => {
    if (silent) return;
    write(JSON.stringify({ severity, message, time: new Date().toISOString(), ...redact(fields) }));
  };
  return { info: log('INFO'), warn: log('WARNING'), error: log('ERROR') };
}
