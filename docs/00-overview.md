# InsightPilot — Hackathon Build Docs

Oct 23, 2026 · Prasad

InsightPilot is an agentic BI analyst: ask a business question in plain English, and it writes guarded SQL, runs it on BigQuery under a cost cap, and explains the result using only numbers it can prove. Built solo in 3 hours on React + Node/Express + MongoDB + FastAPI/LangGraph + Gemini + BigQuery, hosted on Firebase and Cloud Run.

## What each doc answers

| Doc | Answers | Read when |
| --- | --- | --- |
| 01-prd.md | What we build, for whom, MVP vs stretch, acceptance criteria | Before writing any code |
| 02-architecture-api.md | Components, agent graph, schemas, API contracts, repo layout | While building each service |
| 03-security-integrity.md | Threats, controls, SQL validator rules, attack tests | While building the agent and gateway |
| 04-accuracy-performance.md | How we prove answers are right, fast and cheap | Building the eval and metrics page |
| 05-deploy-ops-testing.md | Exact GCP commands, secrets, logging, test plan, fallback | Deploy window and pre-demo |
| 06-build-plan-demo.md | Minute-by-minute plan, cut lines, prompts, demo script | Keep open the whole time |

## Key decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Problem domain | Data & business intelligence | Measurable accuracy, natural fit for BigQuery |
| Dataset | `bigquery-public-data.thelook_ecommerce` (orders, order_items, products, users, inventory_items, distribution_centers, events) | Realistic e-commerce data, free to query, zero ingestion time |
| SQL model | `gemini-3.5-flash` (pinned in env var) | Strong tool use and SQL at Flash cost |
| Cheap model | `gemini-3.5-flash-lite` for the narrative | Cuts cost and latency on the easy step |
| Agent framework | LangGraph in FastAPI | Explicit graph = visible, testable steps and a retry loop |
| Security boundary | Deterministic code, never the LLM | Read-only service account + AST validator + dry-run cost cap |
| Numbers in answers | Computed in Python from BigQuery rows only | LLM writes words; a checker rejects any number it cannot trace |
| App database | MongoDB Atlas M0 (free) | Users, audit log, answer cache — keeps the M in MERN |
| Hosting | Firebase Hosting (web) + Cloud Run in `us-central1` (API + agent) | Same region as the US public dataset; free tiers cover a hackathon |

Check model IDs at minute 0: Gemini 2.5 models were scheduled for shutdown on 16 October 2026, so older tutorials and snippets using `gemini-2.5-*` will 404. Free-tier quotas vary by key and have been reported as low as 20 requests per day for `gemini-3.5-flash` — enable billing or trial credits before the clock starts.

## Judging criteria map

| Criterion | What judges see | Where it's specified |
| --- | --- | --- |
| Security | Live prompt-injection attempt blocked; read-only service account; SELECT-only AST validator; per-query cost cap; Google sign-in; rate limits | 03 |
| Efficiency | Bytes scanned, LLM calls and tokens per question; cache hit returns in under 1 s with 0 LLM calls; Flash-Lite routing | 04 |
| Technology implemented | LangGraph agent with planning, self-correction loop, deterministic verification, rule-based charting | 02 |
| Performance | p50/p95 latency and execution accuracy on a 20-question golden set, shown on a Metrics page | 04 |
| Google technology used | Gemini, BigQuery, Firebase Auth + Hosting, Cloud Run, Secret Manager, Cloud Logging; Vertex AI optional | 02 and 05 |

## Sources

- [Gemini API models list](https://ai.google.dev/models?hl=en)
- [Gemini API model lineup and 2.5 shutdown date](https://claw.aguidetocloud.com/google/gemini-api/models/)
- [Gemini free-tier 429 limits report](https://dev.to/nils44344/gemini-api-429-resourceexhausted-why-your-limit-is-0-68o)
- [BigQuery sandbox limits](https://goo.gle/2ORsEn4)
- [Cloud Run pricing and free tier](https://goo.gle/3Inc1KA)
