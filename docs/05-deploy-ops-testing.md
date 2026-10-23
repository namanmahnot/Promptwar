# 5 · Deployment, Ops & Testing

Two Cloud Run services in `us-central1` plus Firebase Hosting, deployed from source with copy-paste commands. Deploy a `/healthz` skeleton in the first 30 minutes so deploy problems surface early.

## Environments

| Env | Web | API | Agent | Data |
| --- | --- | --- | --- | --- |
| Local | `npm run dev` (Vite, :5173) | `node src/index.js` (:8080) | `uvicorn app.main:app --reload` (:8000) | BigQuery via `gcloud auth application-default login`; Atlas M0 |
| Prod | Firebase Hosting | Cloud Run `insightpilot-api` (public) | Cloud Run `insightpilot-agent` (private) | Same |

Locally the gateway skips the Google ID token when `NODE_ENV=development` and calls `http://localhost:8000`.

## Before the clock: accounts (no code)

- [ ] GCP project created, billing or free-trial credits attached (Gemini free-tier quota alone is too risky)
- [ ] BigQuery: run ``SELECT COUNT(*) FROM `bigquery-public-data.thelook_ecommerce.orders` `` in the console
- [ ] Gemini key created in AI Studio and one test call made with the exact model ID you will use — or Vertex AI enabled
- [ ] Firebase project linked to the GCP project; Google sign-in provider enabled
- [ ] MongoDB Atlas M0 cluster, DB user with `readWrite` on `insightpilot`, network access set, SRV string copied
- [ ] `gcloud`, `firebase-tools`, Node 20, Python 3.12 installed and logged in

Check the hackathon rules on what prep is allowed; account setup is normally fine, pre-written code is not.

## GCP setup (once)

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
gcloud config set project $PROJECT_ID

gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  bigquery.googleapis.com aiplatform.googleapis.com logging.googleapis.com

# least-privilege service accounts
gcloud iam service-accounts create ip-agent --display-name="InsightPilot agent"
gcloud iam service-accounts create ip-api   --display-name="InsightPilot gateway"
AGENT_SA=ip-agent@$PROJECT_ID.iam.gserviceaccount.com
API_SA=ip-api@$PROJECT_ID.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$AGENT_SA --role=roles/bigquery.jobUser
# only if calling Gemini through Vertex AI:
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$AGENT_SA --role=roles/aiplatform.user

# secrets
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
printf '%s' "$MONGO_URI"      | gcloud secrets create mongo-uri --data-file=-
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member=serviceAccount:$AGENT_SA --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding mongo-uri \
  --member=serviceAccount:$API_SA --role=roles/secretmanager.secretAccessor
```

Public datasets are readable by any authenticated principal, so the agent needs no data-viewer role; query jobs are billed to your project through `bigquery.jobUser`. The table allowlist in the validator is what keeps the agent on `thelook_ecommerce`.

## Dockerfiles

```dockerfile
# agent/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
```

```dockerfile
# api/Dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY src ./src
ENV PORT=8080
USER node
CMD ["node", "src/index.js"]
```

## Deploy

```bash
# 1. agent (private)
gcloud run deploy insightpilot-agent --source ./agent --region $REGION \
  --service-account $AGENT_SA --no-allow-unauthenticated \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
  --set-env-vars GCP_PROJECT=$PROJECT_ID,GEMINI_MODEL_SQL=gemini-3.5-flash,GEMINI_MODEL_LITE=gemini-3.5-flash-lite,BQ_MAX_BYTES=1000000000,PROMPT_VERSION=v1 \
  --cpu 1 --memory 1Gi --concurrency 20 --max-instances 3 --timeout 60

AGENT_URL=$(gcloud run services describe insightpilot-agent --region $REGION --format='value(status.url)')
gcloud run services add-iam-policy-binding insightpilot-agent --region $REGION \
  --member=serviceAccount:$API_SA --role=roles/run.invoker

# 2. gateway (public)
gcloud run deploy insightpilot-api --source ./api --region $REGION \
  --service-account $API_SA --allow-unauthenticated \
  --set-secrets MONGO_URI=mongo-uri:latest \
  --set-env-vars AGENT_URL=$AGENT_URL,FIREBASE_PROJECT_ID=$PROJECT_ID,CORS_ORIGINS=https://$PROJECT_ID.web.app,PROMPT_VERSION=v1 \
  --cpu 1 --memory 512Mi --concurrency 40 --max-instances 3 --timeout 60

# 3. web
cd web && npm run build && firebase deploy --only hosting
```

`firebase.json`: `"public": "dist"` with a rewrite of `**` to `/index.html`. Set `VITE_API_URL` to the gateway URL before building.

Gateway → agent call (signed with the gateway's service account):

```js
import { GoogleAuth } from 'google-auth-library';
const auth = new GoogleAuth();
const client = await auth.getIdTokenClient(process.env.AGENT_URL);
const { data } = await client.request({
  url: `${process.env.AGENT_URL}/v1/ask`, method: 'POST',
  data: { question, uid, requestId }, timeout: 45000,
});
```

During judging only: `gcloud run services update insightpilot-agent --region $REGION --min-instances 1` (and the same for the API) to avoid cold starts; set back to 0 afterwards.

## Cost guardrails

```bash
gcloud billing budgets create --billing-account=$BILLING_ACCOUNT_ID \
  --display-name=insightpilot --budget-amount=10USD \
  --threshold-rule=percent=0.5 --threshold-rule=percent=1.0
```

Plus `max-instances 3` on both services, the 1 GB per-query cap, and per-user rate limits. Cloud Run's free tier includes 180,000 vCPU-seconds, 360,000 GiB-seconds and 2 million requests per month (request-based billing, `us-central1`); BigQuery's free tier includes 1 TB of query processing and 10 GB of storage per month.

## Observability

- Both services print **one JSON line per event** to stdout; Cloud Run ships it to Cloud Logging with severity parsed.
- Fields: `severity`, `message`, `requestId`, `uid`, `step`, `ms`, `status`, `code`, `bytes`, `model`. Never tokens, keys or result rows.
- `requestId` is generated by the gateway, sent to the agent in the body and an `X-Request-Id` header, and stored on the audit row — one ID traces a request across services.
- Useful log query: `jsonPayload.requestId="<id>"` across both services.
- BigQuery jobs are labelled `app=insightpilot`, so spend is filterable in job history.
- `/healthz` on both services; the agent's reports whether the schema cache loaded.

## Test plan

| Level | What | Tool | Must pass before demo |
| --- | --- | --- | --- |
| Unit | SQL validator — every rule, pass + fail case | pytest | Yes |
| Unit | Grounding checker (numbers in/out of facts, %, commas, rounding) | pytest | Yes |
| Unit | Facts computation and chart rules | pytest | Nice to have |
| Unit | zod schema rejects non-string / long / empty questions | node:test or Vitest | Nice to have |
| Integration | `/v1/ask` on 3 golden questions locally | curl / pytest + httpx | Yes |
| Security | Attack set A1–A10 against the deployed build | `run_eval.py --attacks` | Yes, 10/10 |
| Eval | 20-question golden set | `run_eval.py` | Run once, numbers on Metrics page |
| Smoke | Checklist below on prod URLs | Browser + curl | Yes |

**Validator test cases (minimum)**: plain SELECT passes; CTE passes; UNION of two SELECTs passes; two statements fail; `DROP TABLE` fails; `DELETE` fails; `INSERT … SELECT` fails; table outside allowlist fails; `INFORMATION_SCHEMA` fails; `users.email` in WHERE fails; `SELECT *` from `users` fails; `SELECT *` from `orders` passes; missing LIMIT gets `LIMIT 1000`; `LIMIT 50000` becomes 1000; `EXTERNAL_QUERY` fails; SQL hidden after a comment (`-- ;DROP`) is handled by the parser, not string matching.

## Smoke test (prod)

- [ ] `GET <api>/healthz` → 200; `GET <agent>/healthz` without a token → 403
- [ ] `POST <api>/api/ask` without a token → 401
- [ ] Sign in on the web app, ask G01 → answer, chart, SQL, trace
- [ ] Ask G01 again → `cached`, under 1 s, 0 LLM calls
- [ ] Ask A2 → blocked with a reason
- [ ] History shows both; Metrics page shows the latest eval run
- [ ] Cloud Logging shows one `requestId` across both services

## Rollback and demo fallback

- Every deploy is a new Cloud Run revision. Roll back: `gcloud run services update-traffic insightpilot-agent --region $REGION --to-revisions=<good-revision>=100`.
- Tag the last working commit `demo-ready`; never deploy after it without re-running the smoke test.
- Record a 2-minute screen capture of the full demo as soon as prod works — your backup if venue Wi-Fi fails.
- Keep the local stack runnable (`npm run dev` + `uvicorn`) as a second fallback.
