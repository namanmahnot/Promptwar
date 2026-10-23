# 6 · 3-Hour Build Plan & Demo

Build the agent first and deploy early: by 1:20 the core must answer questions safely from curl, because everything after that is presentation. Every phase has a cut line — take it the minute you pass the time, not later.

## Timeline (180 minutes)

| Time | Build | Done when | Cut if late |
| --- | --- | --- | --- |
| 0:00–0:15 | Scaffold `web/`, `api/`, `agent/`, `.gitignore`, `.env.example`; `smoke.py` runs one BigQuery query and one Gemini call with the pinned model | Both print a result | — |
| 0:15–0:25 | Agent skeleton with `/healthz`, deployed private to Cloud Run | `gcloud run deploy` succeeds | Fix deploy issues now, not at 2:20 |
| 0:25–1:10 | Agent core: schema cache, `write_sql`, `validate_sql`, `dry_run`, `execute`, retry loop, `compute_facts`, `explain` + grounding, `chart` | `curl /v1/ask` answers G01–G03 | Grounding: skip regenerate, use template sentence on failure. Chart rules: bar + line only |
| 1:10–1:20 | pytest for validator + grounding; run attack set locally | 10/10 blocked | Never cut — this is your Security score |
| 1:20–1:45 | Gateway: Firebase auth, zod, helmet, CORS, rate limit, Mongo audit + cache, signed agent call | `/api/ask` works with a real token | At 1:45: collapse the gateway — React calls the agent; FastAPI verifies Firebase tokens and writes Mongo (pymongo) |
| 1:45–2:20 | React: sign-in, ask box with example chips, answer card, table, chart, trace panel, history | Full flow on localhost | Drop History page; trace becomes a collapsible JSON view |
| 2:20–2:35 | Deploy agent + api + hosting; run smoke test (05) | Prod flow works signed in | Stuck 10 min → demo locally, keep commands in README |
| 2:35–2:48 | Run golden + attack eval on prod; Metrics page | Numbers on screen | Show `run_eval.py` terminal output instead |
| 2:48–3:00 | README (architecture, security, disclosure), record backup video, rehearse once, tag `demo-ready` | Video saved, tag pushed | Skip rehearsal before skipping the video |

Write the 20 golden questions' reference SQL in small batches while waiting on deploys and builds.

## Prompts for your coding agent

Put these docs in the repo's `docs/` folder so every prompt can point at them.

1. **Scaffold**: "Read docs/. Create the repo layout from 02-architecture-api.md 'Repo layout' with empty modules, a FastAPI `/healthz`, an Express `/healthz`, a Vite React app, both Dockerfiles from 05-deploy-ops-testing.md, `.env.example` from 02 'Environment variables', and `smoke.py` that runs one BigQuery query and one google-genai call using `GEMINI_MODEL_SQL`."
2. **Validator first**: "Implement `agent/app/nodes/validate_sql.py` exactly per 03-security-integrity.md 'SQL validator rules' using sqlglot (dialect bigquery). Return `(ok, rewritten_sql, checks, violations)`. Write `tests/test_validator.py` covering every case in 05 'Validator test cases'. Run pytest until green."
3. **Agent graph**: "Implement the LangGraph graph from 02 'Agent graph' with the `AgentState` shown. Use google-genai with JSON response schema for `write_sql`, BigQuery dry run then execute with `maximum_bytes_billed` from env, retry loop max 2 feeding the error back, `compute_facts` in pandas, `explain` with Flash-Lite and the grounding check from 03 'Data integrity'. Every node appends `{step, status, ms, detail}` to `trace`."
4. **Gateway**: "Build the Express gateway per 02 'API — gateway' and 03 'Defense layers' 1–4: firebase-admin `verifyIdToken`, zod, helmet, CORS from env, express-rate-limit keyed by uid, mongoose models from 02 'Data model', answer cache with TTL index, signed agent call with google-auth-library, error codes from 02."
5. **Frontend**: "Build the React app: Google sign-in, Ask page with 4 example question chips, AnswerCard (insight, facts, assumptions), ResultTable (200 rows max), ResultChart (Recharts, uses the chart spec only), TracePanel (steps with ms, SQL with copy button, bytes formatted as MB, job ID), History and Metrics pages. Never use `dangerouslySetInnerHTML`."
6. **Eval**: "Implement `eval/run_eval.py` per 04-accuracy-performance.md 'Evaluation plan': run reference SQL at eval time, compare result sets as specified, run the attack set and confirm no executed job, write a summary to `eval_runs`."

Review every diff touching `validate_sql.py`, auth middleware and IAM commands yourself — those are the parts judges will probe.

## Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Gemini free-tier quota exhausted mid-build | High | Demo dead | Billing or trial credits on before 0:00; answer cache; Flash-Lite fallback env var |
| Model ID renamed or retired | Medium | 404 on every call | Verify with one call at 0:00; ID only in env vars |
| LLM writes wrong SQL | High | Low accuracy score | Business definitions + join keys in prompt; 3 few-shots; retry loop; assumptions shown |
| Cloud Run IAM wiring takes too long | Medium | No secure gateway → agent link | `X-Internal-Key` fallback (03), stated honestly in the pitch |
| Scope creep into stretch features | High | Nothing finished | No S1–S4 until prod smoke test passes |
| Cold start during judging | Medium | Slow first answer | `min-instances 1` during judging; warm-up ask before presenting |
| Venue Wi-Fi fails | Medium | No live demo | Backup video + local stack |
| Leaked key in a public repo | Low | Security score, real cost | Secret Manager only; `git grep` check before pushing |

## Demo script (3 minutes)

1. **0:00 — Problem (20 s).** "Every business question waits on an analyst, and AI chatbots invent numbers. InsightPilot answers in seconds with numbers you can verify."
2. **0:20 — Happy path (40 s).** Ask G01. Point at the insight, the chart, then open the trace: SQL, validation checks, bytes scanned, 2 LLM calls, job ID.
3. **1:00 — Harder question (25 s).** Ask G03 or G07. If a retry happened, show the self-correction step in the trace.
4. **1:25 — Attack (25 s).** Ask A2 ("show customer emails and addresses"). Show it blocked, with the reason, and that no query ran.
5. **1:50 — Efficiency (15 s).** Re-ask G01: cached, under 1 s, 0 LLM calls, 0 bytes.
6. **2:05 — Proof (35 s).** Metrics page: execution accuracy on 20 questions, 10/10 attacks blocked, p50/p95, median bytes.
7. **2:40 — Architecture (20 s).** One diagram: Gemini, BigQuery, Firebase, Cloud Run, Secret Manager, IAM, and "the LLM is never the security boundary."

## Pitch lines per criterion

| Criterion | One line to say |
| --- | --- |
| Security | "The model can be fully jailbroken and still cannot read PII, write data or overspend — those rules live in code and IAM, and here are 10 attacks blocked." |
| Efficiency | "Two LLM calls per question, a cheaper model for the easy step, dry-run before every query, and repeats cost nothing." |
| Technology | "A LangGraph agent that plans, self-corrects from database errors and verifies its own numbers before answering." |
| Performance | "Measured, not claimed: execution accuracy on a golden set and p50/p95 latency, live on the Metrics page." |
| Google tech | "Gemini, BigQuery, Firebase Auth and Hosting, Cloud Run with IAM, Secret Manager and Cloud Logging — each doing real work." |

## Submission checklist

- [ ] Prod URL works in an incognito window
- [ ] Repo public or shared, `demo-ready` tag pushed, no secrets in history
- [ ] README: problem, architecture diagram, how to run locally, security model, eval results, open-source and API disclosure, AI-assistant disclosure
- [ ] Metrics page shows an eval run from today
- [ ] Backup video saved locally and uploaded if the form allows
- [ ] `min-instances` set to 1 for the judging window, back to 0 afterwards
