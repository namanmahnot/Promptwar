# InsightPilot

**Ask a business question in plain English. Get a verified answer, a chart and the SQL behind it in seconds, and nothing unsafe or expensive ever runs.**

## Problem

Business owners and ops managers wait on an analyst for every ad-hoc question ("which categories lost revenue last quarter?"). Dashboards only answer the questions someone predicted. Generic AI chatbots answer instantly but invent numbers, and a wrong number is worse than no number.

InsightPilot is an agentic BI analyst over the BigQuery public dataset `thelook_ecommerce`. A LangGraph agent writes SQL with Gemini. Deterministic code validates and cost-caps that SQL, then BigQuery runs it. **Every number in the answer is computed from the result rows, never written by the model**, and the SQL, BigQuery job ID and per-step trace are shown with every answer.

## Architecture

```mermaid
flowchart TB
  user["Browser · React app<br/>Google sign-in (Firebase Auth)"]
  api["FastAPI service · Cloud Run<br/>token check · validation · rate limit · cache · audit<br/>also serves the React build"]
  fs[("Firestore<br/>audit log · answer cache (6 h TTL) · eval runs")]
  gemini["Gemini 3.5 Flash (SQL)<br/>Gemini 3.5 Flash-Lite (narrative)"]
  bq[("BigQuery<br/>thelook_ecommerce · 1 GB cap")]
  user -- "HTTPS + Firebase ID token" --> api
  api --> fs
  api --> gemini
  api -- "validated SELECT only" --> bq
  subgraph agent["LangGraph agent (in-process)"]
    direction LR
    a1["prefilter<br/>regex"] --> a2["write_sql<br/>Flash, JSON"] --> a3["validate_sql<br/>sqlglot AST"] --> a4["dry_run<br/>≤ 1 GB"] --> a5["execute<br/>30 s, capped"] --> a6["facts<br/>Python"] --> a7["chart<br/>rules"] --> a8["explain<br/>Flash-Lite + grounding"]
    a5 -. "SQL error → retry with error (max 2)" .-> a2
  end
  api -.- agent
```

| Path | What |
| --- | --- |
| [agent/app/main.py](agent/app/main.py) | HTTP API: auth, validation, rate limit, cache, audit, serves the web app |
| [agent/app/graph.py](agent/app/graph.py) | LangGraph agent and trace |
| [agent/app/nodes/](agent/app/nodes/) | prefilter, write_sql, validate_sql, facts, chart, explain |
| [agent/app/security.py](agent/app/security.py) · [store.py](agent/app/store.py) | Token verification, rate limiter, headers, body cap · Firestore store |
| [agent/eval/](agent/eval/) | 20 golden questions, 10 attacks, `run_eval.py` |
| [web/](web/) | React 19 + Vite + Tailwind + Recharts: Ask, History, Metrics |
| [docs/](docs/) | PRD, API spec, security model, eval plan, build plan |

## Security

The LLM is treated as untrusted input. Every guarantee is enforced by deterministic code and IAM, so a fully jailbroken model can at worst produce a **blocked** request.

| Layer | Mechanism | Code |
| --- | --- | --- |
| Identity | Firebase ID token verified on every `/api` route (signature, expiry, audience). The uid comes only from the token. | `security.py`, `main.py: current_user` |
| Input | Pydantic: string only, 3–500 chars, control characters stripped, extra fields rejected (400). 10 KB body cap enforced at the ASGI layer, even without `Content-Length` (413). | `main.py: AskBody`, `security.py: BodySizeLimit` |
| Abuse | 10 asks/min and 100/day per user (429 + `Retry-After`). Cloud Run `--max-instances 3`. | `security.py: RateLimiter` |
| Pre-filter | Regex, no LLM: destructive SQL verbs, "ignore previous", "system prompt", personal-data asks → `UNSAFE_REQUEST`; poems, other datasets, `INFORMATION_SCHEMA` → `OUT_OF_SCOPE` | `nodes/prefilter.py` |
| LLM sandbox | The model sees only allowlisted tables with PII columns removed, and must return JSON `{answerable, sql, assumptions}` | `schema_cache.py`, `prompts/write_sql.v1.txt` |
| **SQL validator** | sqlglot AST (bigquery dialect): exactly one statement; SELECT / WITH / set-ops only; no DML, DDL or scripting node anywhere; tables must be in the `thelook_ecommerce` allowlist; no `INFORMATION_SCHEMA`; no PII columns (including via aliases, CTEs and whole-row `TO_JSON_STRING(u)`); no `SELECT *` over `users`/`events`; no `EXTERNAL_QUERY`, `ML.*`, `AI.*`; no cartesian joins; LIMIT added or lowered to 1000. Violations → `UNSAFE_SQL`, **never retried**. | `nodes/validate_sql.py` |
| Cost | Dry run first, blocked above 1 GB (`COST_LIMIT`). Execution with `maximum_bytes_billed`, 30 s timeout, label `app=insightpilot`. | `bq.py`, `graph.py` |
| Least privilege | The runtime service account has only `roles/bigquery.jobUser`, `roles/datastore.user` and `secretAccessor` on one secret. The dataset is public read-only anyway. | Deploy below |
| Secrets | Gemini key in Secret Manager. `.env*` git-ignored. The frontend bundle holds only the Firebase web config (public by design). CI fails on committed keys. | `.gitignore`, `.github/workflows/ci.yml` |
| Headers | CSP, `nosniff`, `X-Frame-Options: DENY`, HSTS, Referrer-Policy, Permissions-Policy. CORS is off by default (same origin) or locked to `CORS_ORIGINS`. | `security.py: SECURITY_HEADERS` |
| Output | React escapes everything; no `dangerouslySetInnerHTML` (ESLint `react/no-danger` = error). | `web/eslint.config.js` |
| Audit + logs | One Firestore record per request: uid, question, SQL, job ID, bytes, status, code, trace, model, latency. Result rows are **not** stored. JSON logs (`severity`, `request_id`, `uid`, `step`, `ms`, `code`) never include tokens, keys or rows, and keys are redacted by name. | `main.py: _audit_record`, `logging_config.py` |

## Efficiency

- **2 LLM calls per question** (SQL + narrative). Pre-filter, validation, facts and charting use no LLM.
- **Model routing**: Flash writes the SQL; the cheaper Flash-Lite writes the narrative from the facts list only (never raw rows).
- **Answer cache**: key = `sha256(normalized question + model + prompt version)`, 6 h TTL in Firestore. A repeat returns `cached: true` with **0 LLM calls and 0 bytes scanned**.
- **BigQuery**: dry run before every query, `use_query_cache=True`, LIMIT 1000; the UI shows 200 rows.
- **Prompt size**: PII and geography columns stripped from the schema DDL. The schema is built once at startup from table metadata, which is free, unlike a billed `INFORMATION_SCHEMA` query.
- **Gemini resilience**: 20 s timeout, 1 retry on 429/5xx with backoff, then one fallback to `GEMINI_MODEL_LITE`. Model IDs come only from env.
- **Frontend**: Firebase SDK and Recharts are lazy-loaded chunks.

## Technology implemented

- **LangGraph state machine** with typed state, conditional edges and a self-correction loop: a BigQuery error is fed back into `write_sql` (max 2 retries), while safety violations end the graph.
- **Deterministic verification**: facts (totals, top/bottom, change %, share) are computed in Python. A **grounding checker** normalises commas, %, currency and k/M/B and compares numbers at the precision written. If any number in the narrative isn't in the facts or the question, the narrative is regenerated once, then replaced by a template built from facts.
- **Rule-based charts**: date + number → line; category + number with ≤ 20 rows → bar; otherwise a table.
- **Full trace**: every node appends `{step, status, ms, detail}`, and LLM calls and tokens are counted. The UI shows it in a collapsible panel with the SQL (copy button), bytes in MB, job ID and LLM calls.

## Performance

Measured, not claimed: `python -m eval.run_eval --save` runs the **20 golden questions** ([golden.jsonl](agent/eval/golden.jsonl)). Each reference SQL runs **at eval time** (the dataset refreshes, so no answers are hard-coded), and result sets are compared ignoring column names, with order only when `order_matters` and floats within 0.01 relative. It then runs the **10 attacks** ([attacks.jsonl](agent/eval/attacks.jsonl)); an attack passes only if it is blocked **and no BigQuery job executed**. Results go to Firestore and the Metrics page.

| Metric | Target | Latest run |
| --- | --- | --- |
| Execution accuracy (20 questions) | ≥ 80% | _run `python -m eval.run_eval --save` after deploy_ |
| Valid SQL rate | ≥ 95% | _pending_ |
| Attacks blocked, no job executed | 10 / 10 | 10 / 10 offline, with a model that obeys the attacker (`test_attack_set_is_fully_blocked_even_with_a_compromised_model`) |
| Ungrounded numbers in answers | 0 | 0 by construction (grounding check plus template fallback) |
| Latency p50 / p95 (uncached) | ≤ 8 s / ≤ 15 s | _pending_ |
| Cached repeat | ≤ 1 s, 0 LLM calls, 0 bytes | verified in `test_repeat_question_is_cached_with_zero_cost` |
| Median bytes scanned | report (cap 1 GB) | _pending_ |
| Mean LLM calls | 2 typical | 2 (`test_happy_path_answers_with_two_llm_calls`) |

## Google technology used

| Product | Role |
| --- | --- |
| **Gemini 3.5 Flash / Flash-Lite** (google-genai) | Structured SQL generation / grounded narrative |
| **BigQuery** | Warehouse (`bigquery-public-data.thelook_ecommerce`): dry run, cost cap, result cache, job labels |
| **Firebase Authentication** | Google sign-in; ID tokens verified server-side with firebase-admin |
| **Cloud Firestore** | Audit log, answer cache with TTL, eval runs |
| **Cloud Run** | One container, `--max-instances 3`, scales to zero |
| **Secret Manager** | Gemini API key |
| **Cloud Logging** | Structured JSON logs with `severity` and `request_id` |
| **Cloud Build / Artifact Registry** | `gcloud run deploy --source .` |
| Firebase Hosting (optional) | Static hosting of the web app ([firebase.json](firebase.json)) when the API runs elsewhere |

## Code quality, testing and accessibility

- **Tests**: 143 pytest tests and 18 Vitest tests, all green, with no network and no credentials (Gemini, BigQuery, Firebase and Firestore are faked):
  - [test_validator.py](agent/tests/test_validator.py): a passing and a failing case for every validator rule, including the `-- ;DROP` comment trick.
  - [test_grounding.py](agent/tests/test_grounding.py) for the number-grounding checker.
  - [test_graph.py](agent/tests/test_graph.py): retry loop, cost cap, outages, template fallback.
  - [test_api.py](agent/tests/test_api.py): 401, 400, 413, 422, 429, cache, history ownership, headers, SPA serving.
  - [test_evaluation.py](agent/tests/test_evaluation.py) for the result comparator and the attack set.
  - Web tests include **axe-core** accessibility checks on every page state.
- **Lint**: ruff (with bandit-style `S` rules) and ESLint (React, hooks, jsx-a11y *strict*). CI runs lint, tests, the build and a secret scan on every push.
- **Accessibility**:
  - Navigation and focus: skip link, landmarks, `aria-current`, and focus moves to each new answer and page.
  - Announcements: errors via `role="alert"`, progress via `role="status"`.
  - Charts are `role="img"` with a text summary, and the full table is always rendered with `th scope`.
  - Visual: status is never shown by colour alone, 44 px targets, visible focus rings, `prefers-reduced-motion` respected.

## Run locally

```bash
# API + agent (needs BigQuery access: gcloud auth application-default login, or GOOGLE_SERVICE_ACCOUNT_JSON)
cd agent
python -m venv .venv && .venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                                     # set GEMINI_API_KEY
set -a && . ./.env && set +a
python smoke.py                                          # 1 BigQuery query + 1 Gemini call per model
uvicorn app.main:app --reload --port 8000

# Web (proxies /api to :8000)
cd web && npm install
VITE_AUTH_DEV_BYPASS=true npm run dev                    # http://localhost:5173, signs in as a local dev user
```

`AUTH_DEV_BYPASS` accepts the literal token `dev` and is **refused at startup** unless `APP_ENV=development`.

Tests and lint: `cd agent && pytest && ruff check app tests eval` · `cd web && npm run lint && npm test`.

## Deploy to Cloud Run (copy-paste)

Requires a billing-enabled project. The Firebase project `promptwar-naman` doubles as the GCP project.

```bash
export PROJECT_ID=promptwar-naman REGION=us-central1
gcloud config set project $PROJECT_ID

# 1. APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com bigquery.googleapis.com firestore.googleapis.com logging.googleapis.com

# 2. Firestore (Native mode) + TTL on cached answers
gcloud firestore databases create --location=nam5
gcloud firestore fields ttls update expiresAt --collection-group=cache --enable-ttl

# 3. Least-privilege runtime service account
gcloud iam service-accounts create insightpilot --display-name="InsightPilot runtime"
export SA=insightpilot@$PROJECT_ID.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=roles/bigquery.jobUser
gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=roles/datastore.user

# 4. Gemini key in Secret Manager, readable only by that account
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
gcloud secrets add-iam-policy-binding gemini-api-key --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor

# 5. Firebase web config (public) for the build, then deploy
cp web/.env.example web/.env.production   # fill VITE_FIREBASE_* from: firebase apps:sdkconfig web
gcloud run deploy insightpilot --source . --region $REGION --service-account $SA --allow-unauthenticated \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
  --set-env-vars GCP_PROJECT=$PROJECT_ID,GEMINI_MODEL_SQL=gemini-3.5-flash,GEMINI_MODEL_LITE=gemini-3.5-flash-lite,BQ_MAX_BYTES=1000000000,PROMPT_VERSION=v1 \
  --cpu 1 --memory 1Gi --concurrency 20 --max-instances 3 --timeout 60

# 6. $10 budget alert
gcloud billing budgets create --billing-account=$BILLING_ACCOUNT_ID --display-name=insightpilot \
  --budget-amount=10USD --threshold-rule=percent=0.5 --threshold-rule=percent=1.0
```

Then, in the Firebase console, go to Authentication → Sign-in method → enable **Google**, and under Settings → Authorized domains add the `*.run.app` hostname. Smoke test: `curl $URL/healthz` → `{"ok":true,"schemaLoaded":true}`; `curl -X POST $URL/api/ask` → 401.

**No billing (Firebase Spark)?** Deploy the same Dockerfile on Render's free tier with [render.yaml](render.yaml). Set `GEMINI_API_KEY` and `GOOGLE_SERVICE_ACCOUNT_JSON`, the key of a service account with only BigQuery Job User and Cloud Datastore User; Firestore and the BigQuery sandbox both work without billing. Add the `onrender.com` hostname to Firebase's authorized domains.

Known gaps: rate limits are in memory per instance (at most 3); the Render path uses a service-account key instead of attached identity.

## Disclosure

All application code was written during the event with the help of an AI coding assistant (**Claude Code**). The design docs in [docs/](docs/) were prepared before the build.

- **Libraries**: FastAPI, Uvicorn, Pydantic, LangGraph, google-genai, google-cloud-bigquery, google-cloud-firestore, firebase-admin, sqlglot, pytest, httpx, ruff; React, React Router, Vite, Tailwind CSS, Recharts, Firebase JS SDK, Vitest, Testing Library, axe-core, jsdom, ESLint.
- **APIs and services**: Gemini API (`gemini-3.5-flash`, `gemini-3.5-flash-lite`), BigQuery, Firebase Authentication, Cloud Firestore, Cloud Run, Secret Manager, Cloud Logging.
- **Dataset**: `bigquery-public-data.thelook_ecommerce` (synthetic e-commerce data published by Google).
