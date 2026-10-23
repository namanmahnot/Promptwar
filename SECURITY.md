# Security policy

## Reporting a vulnerability

Please report security issues privately via GitHub **Security → Report a vulnerability** on this repository rather than opening a public issue. We aim to acknowledge reports within 72 hours.

## Threat model and controls

InsightPilot treats the LLM as untrusted input. All guarantees are enforced by deterministic code and IAM; see the [Security section of the README](README.md#security) and [docs/03-security-integrity.md](docs/03-security-integrity.md).

| Threat | Control | Verified by |
| --- | --- | --- |
| Prompt injection → destructive SQL | Regex pre-filter; sqlglot AST validator allows one read-only statement; read-only service account | `test_validator.py`, attack set A1/A3/A9 |
| PII exfiltration | PII columns hidden from the model and rejected by the validator (incl. aliases, CTEs, whole-row structs) | `test_validator.py`, attacks A2/A10 |
| Other datasets / metadata | Table allowlist; `INFORMATION_SCHEMA` rejected | attacks A4/A5 |
| Denial of wallet | Dry run ≤ 1 GB, `maximum_bytes_billed`, no cartesian joins, LIMIT 1000, rate limits, max 3 instances | `test_graph.py`, attack A6 |
| Unauthenticated use | Firebase ID token verified on every `/api` route | `test_api.py` (401) |
| Abuse | 10/min and 100/day per user, 10 KB body cap | `test_api.py` (429, 413) |
| XSS | React escaping, strict CSP, ESLint `react/no-danger` | lint, `test_api.py` headers |
| Secret leakage | Secret Manager / env only, `.env*` ignored, CI secret scan, logs redact key-like fields | CI |
| Vulnerable dependencies | `pip-audit` and `npm audit` in CI, CodeQL, Dependabot | CI |

## Supported versions

Only the `main` branch is supported.
