# 1 · Product Requirements (PRD)

The MVP answers plain-English business questions over BigQuery with a verified number, a chart and the SQL behind it, and blocks anything unsafe or too expensive.

## Problem

Business owners and ops managers wait on an analyst for every ad-hoc question ("which categories lost revenue last quarter?"). Dashboards answer only the questions someone predicted. Generic AI chatbots answer instantly but invent numbers, and a wrong number is worse than no number.

InsightPilot closes that gap: answers in seconds, every number traceable to a BigQuery job, every query safe and cost-capped.

## Users

| Persona | Needs | What they see |
| --- | --- | --- |
| Ops / business manager (no SQL) | Fast, trustworthy answers | Insight sentence, chart, key numbers |
| Analyst / engineer | Speed, but must verify | Generated SQL, agent trace, bytes scanned, job ID |
| Judge / admin | Proof it is safe and accurate | Metrics page: eval accuracy, block rate, latency, cost |

## Success metrics

| Metric | Target | Measured by |
| --- | --- | --- |
| Execution accuracy (golden set, 20 questions) | ≥ 80% | `run_eval.py` result-set match |
| Attack prompts blocked (10 prompts) | 10 / 10 | Security test suite |
| Unsupported numbers in insight text | 0 | Number-grounding checker |
| p50 latency, uncached | ≤ 8 s | Per-step timers in trace |
| p50 latency, cached repeat | ≤ 1 s | Same |
| Bytes scanned per query | Hard cap 1 GB; report median | BigQuery dry run + job stats |
| LLM calls per question | 2 typical, ≤ 4 with retries | Trace counter |

## Scope

**MVP — must ship in 3 hours**

| ID | Feature |
| --- | --- |
| F1 | Google sign-in (Firebase Auth) |
| F2 | Ask a question → insight text + key facts + table + chart |
| F3 | Agent trace panel: SQL, validation result, bytes scanned, retries, per-step timing |
| F4 | SQL guardrails: SELECT-only, table/column allowlist, PII denylist, LIMIT, dry-run cost cap |
| F5 | Self-correction: on SQL error, retry with the error message, max 2 retries |
| F6 | History of my questions (MongoDB) |
| F7 | Answer cache for repeated questions |
| F8 | Metrics page: latest eval results + live latency/bytes aggregates |

**Stretch — only after MVP is deployed**

| ID | Feature |
| --- | --- |
| S1 | Saved questions + "Run monitor": re-runs them and flags week-over-week changes beyond 2 standard deviations |
| S2 | Cloud Scheduler triggers S1 daily and stores a digest |
| S3 | Follow-up questions using the previous SQL as context |
| S4 | CSV export of results |

**Out of scope**: write/DML queries, uploading your own data, multi-tenant orgs, voice input, non-English questions.

## User stories and acceptance criteria

1. **Ask a question.** As a manager, I ask "Top 5 product categories by revenue in the last 90 days" and get an answer.
   - Given I am signed in, when I submit a 3–500 character question, then I get insight text, a facts list, a table (≤ 200 rows shown) and a chart if the shape allows.
   - Every number in the insight text appears in the computed facts.
   - The response shows the SQL and bytes scanned.
2. **See why I can trust it.** As an analyst, I open the trace and see each step's status and time, the final SQL, the BigQuery job ID and any retries.
3. **Blocked when unsafe.** As the system owner, when someone asks to delete data, read emails or addresses, query other datasets or scan too much, the request returns a `blocked` status with a reason code, and no BigQuery job runs (except a dry run).
4. **Out of scope.** When a question is not about the dataset ("write a poem"), I get a clear "I can only answer questions about the store's data" message and examples.
5. **Fast repeat.** When I ask the same question again within 6 hours, it returns from cache in under 1 s with 0 LLM calls, marked `cached`.
6. **History.** I see my last 20 questions with status, and clicking one reopens its full answer.
7. **Proof page.** A judge opens Metrics and sees execution accuracy, block rate, p50/p95 latency and median bytes scanned from the latest eval run, with its timestamp.

## Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | All `/api/*` routes except `/healthz` require a valid Firebase ID token |
| FR-2 | Questions are validated: string, 3–500 chars, trimmed, control characters stripped |
| FR-3 | The agent may only query allowlisted tables in `thelook_ecommerce` |
| FR-4 | Generated SQL passes the validator (03-security-integrity.md) before any dry run |
| FR-5 | Every query is dry-run first; above 1 GB it is blocked with `COST_LIMIT` |
| FR-6 | Executed jobs set `maximum_bytes_billed` = 1 GB and a 30 s timeout |
| FR-7 | On SQL error the agent retries with the error text, max 2 retries |
| FR-8 | Facts (totals, top item, min/max, change %) are computed in Python from result rows |
| FR-9 | Insight text is rejected and regenerated once if it contains a number not in facts; second failure falls back to a template sentence |
| FR-10 | Chart type is chosen by rules from column types, not by the LLM |
| FR-11 | Every request writes one audit record: user, question, SQL, job ID, bytes, status, timings, model, prompt version |
| FR-12 | Rate limit: 10 asks per minute and 100 per day per user |

## Non-functional requirements

| Area | Requirement |
| --- | --- |
| Security | Least-privilege service accounts; secrets only in Secret Manager; agent service not publicly invocable; no PII columns ever queried |
| Performance | p50 ≤ 8 s uncached, ≤ 1 s cached; UI shows step progress so waits feel shorter |
| Efficiency | 2 LLM calls typical; BigQuery result cache on; median bytes scanned reported |
| Reliability | Timeouts on every external call; graceful errors with codes; no crash on bad model output |
| Accuracy | ≥ 80% execution accuracy; 0 ungrounded numbers |
| Observability | Structured JSON logs with request ID across both services; audit records in MongoDB |
| Usability | Example questions on the empty state; works on a laptop and a phone |
| Cost | Stays inside free tiers / trial credits; budget alert set |

## Assumptions and constraints

- One developer, 3 hours, MERN + Python, AI-assisted coding allowed.
- Read-only access to a public dataset; no data ingestion.
- The dataset is synthetic and refreshed regularly, so expected answers are computed at eval time, never hard-coded.
- English questions only.

## Originality and disclosure

All application code is written during the event. Disclose in the README: React, Vite, Tailwind, Recharts, Firebase JS SDK, Express, helmet, express-rate-limit, zod, firebase-admin, mongoose, google-auth-library, FastAPI, LangGraph, google-genai, google-cloud-bigquery, sqlglot, pandas, pytest; Gemini models; BigQuery public dataset `thelook_ecommerce`; any AI coding assistant used.
