# 4 · Accuracy, Performance & Efficiency

We prove quality with numbers on a Metrics page: execution accuracy on 20 golden questions, 10/10 attacks blocked, p50/p95 latency, bytes scanned and LLM calls per question.

## Accuracy strategy

| Risk | Mitigation |
| --- | --- |
| Wrong table or join | Compact schema DDL with column descriptions and join keys (`order_items.order_id → orders.order_id`, `order_items.product_id → products.id`, `orders.user_id → users.id`) |
| Wrong business definition | Definitions in the prompt: revenue = `SUM(sale_price)` on `order_items` with `status = 'Complete'`; profit = `sale_price - products.cost`; "last N days" uses `CURRENT_DATE()` |
| Ambiguous question | Model lists `assumptions`, shown under the answer ("Assumed revenue counts completed items only") |
| SQL error | Retry with BigQuery's error message, max 2 |
| Hallucinated numbers | Facts computed in pandas; grounding checker on the narrative |
| Silent wrong answer | SQL + job ID + row count always visible; empty results stated plainly |
| Model drift mid-event | Model ID pinned in env var, recorded on every audit row |

## Evaluation plan

**Golden set** (`eval/golden.jsonl`): 20 questions, each with a hand-written reference SQL. One line per item:

```json
{"qid": "G01", "question": "Top 5 product categories by revenue in the last 90 days", "reference_sql": "SELECT p.category, ROUND(SUM(oi.sale_price), 2) AS revenue FROM `bigquery-public-data.thelook_ecommerce.order_items` oi JOIN `bigquery-public-data.thelook_ecommerce.products` p ON oi.product_id = p.id WHERE oi.status = 'Complete' AND DATE(oi.created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) GROUP BY 1 ORDER BY 2 DESC LIMIT 5", "order_matters": true}
```

The dataset is refreshed regularly, so the runner executes the reference SQL at eval time and compares result sets — no hard-coded expected numbers.

**Starter questions** (write the other 10 the same way):

| ID | Question | Tests |
| --- | --- | --- |
| G01 | Top 5 product categories by revenue in the last 90 days | join, filter, rank |
| G02 | Number of orders per month in 2025 | date truncation |
| G03 | Return rate by product department | conditional ratio |
| G04 | Average order value by country, top 10 | join users, aggregate |
| G05 | Which traffic source brought the most users? | single-table group |
| G06 | Top 10 brands by total profit | cost join, derived metric |
| G07 | Average days from order to delivery by month | date diff |
| G08 | Share of orders by status | percentage of total |
| G09 | How many users signed up each year? | simple trend |
| G10 | Which distribution center shipped the most items? | multi-hop join |

**Metrics computed by `run_eval.py`**

| Metric | Definition | Target |
| --- | --- | --- |
| Execution accuracy | Share of questions whose result set matches the reference (column names ignored; row order compared only when `order_matters`; floats equal within 0.01 relative) | ≥ 80% |
| Valid SQL rate | Share that pass the validator and execute without error (after retries) | ≥ 95% |
| Self-correction rate | Share that needed a retry and then passed | Report |
| Attack block rate | Attack set (03) blocked with no executed job | 100% |
| Grounding violations | Insight numbers not traceable to facts | 0 |
| Latency p50 / p95 | End-to-end agent time per question | ≤ 8 s / ≤ 15 s |
| Median bytes processed | From job statistics | Report |
| Mean LLM calls and tokens | From trace counters | Report |

Results are saved to `eval_runs` and shown on the Metrics page with the run timestamp, model ID and prompt version.

## Latency budget (uncached, target)

| Step | Budget | How we hit it |
| --- | --- | --- |
| Gateway auth + validation + cache lookup | 0.15 s | Token verify uses cached Google certs; indexed hash lookup |
| Pre-filter | 0.01 s | Regex only |
| Write SQL (Gemini Flash) | 2.5 s | Short structured output; schema prompt kept compact |
| Validate | 0.02 s | Local AST parse |
| Dry run | 0.4 s | Same region as dataset |
| Execute | 1.5 s | Result cache; LIMIT 1000 |
| Facts + chart | 0.05 s | pandas on ≤ 1000 rows |
| Explain (Flash-Lite) | 1.5 s | Facts only in the prompt, not raw rows |
| Network and overhead | 0.5 s | Both services in `us-central1` |
| **Total p50** | **≈ 6.6 s** | Target ≤ 8 s; cached ≤ 1 s |

These are planning budgets, not measurements — replace them with real p50s from the trace once the eval runs.

Perceived speed: the UI shows step-by-step progress ("Writing SQL… Validating… Running on BigQuery…") from the trace. Server-sent events are a stretch goal; a simple progress animation keyed to typical step times is enough for the MVP.

## Efficiency levers

| Lever | Setting | Effect |
| --- | --- | --- |
| Model routing | Flash for SQL, Flash-Lite for narrative | Cheaper, faster easy step |
| LLM calls per question | 2 typical; no LLM in pre-filter, validate, facts, chart | Fewer calls, fewer failure points |
| Prompt size | PII columns and unused columns stripped from schema DDL | Fewer input tokens per call |
| Explain input | Facts list only, never raw rows | Small, fixed-size prompt |
| Answer cache | MongoDB, key = hash(normalized question + model + prompt version), TTL 6 h | Repeat question: 0 LLM calls, 0 BigQuery bytes |
| BigQuery result cache | `use_query_cache=True` | Identical SQL re-runs are not billed |
| Dry run first | Every query | Blocks expensive queries before they cost anything |
| Row caps | Query LIMIT 1000, UI renders 200, Mongo stores 50 | Bounded memory and payload size |
| Compute | Cloud Run 1 vCPU / 512 MiB (api), 1 vCPU / 1 GiB (agent), concurrency 20, `max-instances` 3 | Bounded cost; scales to zero |
| Cold starts | `min-instances=1` only during judging | Fast first request without paying all day |

Normalization for the cache key: lowercase, trim, collapse whitespace, strip trailing punctuation. Relative-date questions ("last 90 days") expire with the 6 h TTL, which keeps them fresh enough for a demo.

## Reliability

| Call | Timeout | Retry | Fallback |
| --- | --- | --- | --- |
| Gateway → agent | 45 s | None (agent retries internally) | `TIMEOUT` with request ID |
| Agent → Gemini | 20 s | 1 retry on 429/5xx with 1 s backoff | Switch to `GEMINI_MODEL_LITE` once, then `LLM_UNAVAILABLE` |
| Agent → BigQuery dry run | 10 s | 1 retry on 5xx | `SQL_FAILED` |
| Agent → BigQuery execute | 30 s | Via the graph's SQL retry loop | `SQL_FAILED` |
| Gateway → MongoDB | 5 s | Driver default | Answer still returned; audit write failure logged |

The agent never crashes on bad model output: JSON parsing errors count as a failed attempt and enter the retry loop.

## Metrics page contents

- Latest eval run: execution accuracy, valid SQL rate, attack block rate, p50/p95, median bytes, mean LLM calls, timestamp, model, prompt version.
- Live (last 100 queries): count by status, cache hit rate, p50 latency, median bytes scanned.
- A table of the 20 golden questions with pass/fail and time — judges can click one to see its SQL.
