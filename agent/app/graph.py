"""The LangGraph agent: prefilter → write_sql → validate → dry_run → execute → facts → chart → explain.

SQL errors loop back to write_sql with the error text (max 2 retries). Safety violations
and cost-limit hits end the graph immediately and are never retried.
"""

from __future__ import annotations

import logging
import operator
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.bq import QueryError, Warehouse
from app.config import MAX_ROWS, MAX_SQL_ATTEMPTS, Settings
from app.llm import Llm, LlmUnavailable
from app.nodes.chart import choose_chart
from app.nodes.explain import explain
from app.nodes.facts import compute_facts
from app.nodes.prefilter import prefilter
from app.nodes.validate_sql import validate_sql
from app.nodes.write_sql import SQL_PLAN_SCHEMA, build_prompt, parse_plan
from app.schema_cache import SchemaCache

log = logging.getLogger(__name__)

Status = Literal["running", "answered", "blocked", "failed"]


def _sum_counts(left: dict, right: dict) -> dict:
    return {key: left.get(key, 0) + right.get(key, 0) for key in left.keys() | right.keys()}


class AgentState(TypedDict, total=False):
    request_id: str
    question: str
    sql: str | None
    assumptions: list[str]
    attempts: int  # write_sql calls so far, max MAX_SQL_ATTEMPTS
    last_error: str | None  # fed back into write_sql on retry
    bytes_estimate: int | None
    bytes_processed: int | None
    cache_hit: bool
    job_id: str | None
    columns: list[dict]
    rows: list[dict]
    facts: list[dict]  # the only numbers the insight may use
    insight: str | None
    insight_source: str | None
    chart: dict | None
    status: Status
    code: str | None
    message: str | None
    model: str | None
    trace: Annotated[list[dict], operator.add]
    llm: Annotated[dict, _sum_counts]


NodeResult = tuple[dict, str, str]  # (state update, trace status, trace detail)


@dataclass
class Dependencies:
    settings: Settings
    llm: Llm
    warehouse: Warehouse
    schema: SchemaCache


def _timed(step: str, fn: Callable[[AgentState], NodeResult]) -> Callable[[AgentState], dict]:
    def run(state: AgentState) -> dict:
        start = time.perf_counter()
        update, status, detail = fn(state)
        ms = round((time.perf_counter() - start) * 1000)
        update["trace"] = [{"step": step, "status": status, "ms": ms, "detail": detail}]
        log.info(
            "step",
            extra={"request_id": state.get("request_id"), "step": step, "status": status, "ms": ms},
        )
        return update

    return run


def _blocked(code: str, message: str) -> dict:
    return {"status": "blocked", "code": code, "message": message}


def _retry_or_fail(attempts: int, error: str) -> dict:
    if attempts >= MAX_SQL_ATTEMPTS:
        return {
            "status": "failed",
            "code": "SQL_FAILED",
            "message": f"Could not produce a working query after {attempts} attempts.",
            "last_error": error,
        }
    return {"last_error": error}


def _llm_usage(result) -> dict:
    return {"calls": 1, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}


def build_graph(deps: Dependencies):
    settings = deps.settings

    def prefilter_node(state: AgentState) -> NodeResult:
        result = prefilter(state["question"])
        if not result.ok:
            return {**_blocked(result.code, result.reason), "question": result.question}, "blocked", result.code
        return {"question": result.question}, "ok", "no unsafe patterns"

    def write_sql_node(state: AgentState) -> NodeResult:
        attempts = state.get("attempts", 0) + 1
        prompt = build_prompt(
            state["question"],
            deps.schema.ddl or "",
            settings.prompt_version,
            previous_sql=state.get("sql"),
            previous_error=state.get("last_error"),
        )
        try:
            result = deps.llm.generate(prompt, model=settings.model_sql, json_schema=SQL_PLAN_SCHEMA)
        except LlmUnavailable as err:
            update = {
                "attempts": attempts,
                "status": "failed",
                "code": "LLM_UNAVAILABLE",
                "message": "The language model is temporarily unavailable. Please try again shortly.",
            }
            return update, "error", str(err)

        usage = {"attempts": attempts, "llm": _llm_usage(result), "model": result.model}
        try:
            plan = parse_plan(result.text)
        except ValueError as err:
            return {**usage, **_retry_or_fail(attempts, str(err))}, "retry", str(err)

        if not plan.answerable:
            message = "I can only answer questions about the store's orders, products, customers and traffic."
            return {**usage, **_blocked("OUT_OF_SCOPE", message)}, "blocked", "model: not answerable"
        update = {**usage, "sql": plan.sql, "assumptions": plan.assumptions, "last_error": None}
        return update, "ok", f"attempt {attempts}, {result.model}"

    def validate_node(state: AgentState) -> NodeResult:
        result = validate_sql(state["sql"] or "")
        if result.ok:
            return {"sql": result.sql}, "ok", ", ".join(result.checks)
        detail = "; ".join(result.violations)
        if result.retryable:
            return _retry_or_fail(state["attempts"], detail), "retry", detail
        return _blocked("UNSAFE_SQL", result.violations[0]), "blocked", detail

    def dry_run_node(state: AgentState) -> NodeResult:
        try:
            estimate = deps.warehouse.dry_run(state["sql"])
        except QueryError as err:
            return _retry_or_fail(state["attempts"], str(err)), "retry", str(err)
        detail = f"{estimate:,} bytes estimated (cap {settings.max_bytes:,})"
        if estimate > settings.max_bytes:
            message = f"This query would scan {estimate / 1e9:.1f} GB, above the 1 GB limit. Try a narrower question."
            return {"bytes_estimate": estimate, **_blocked("COST_LIMIT", message)}, "blocked", detail
        return {"bytes_estimate": estimate}, "ok", detail

    def execute_node(state: AgentState) -> NodeResult:
        try:
            result = deps.warehouse.execute(state["sql"])
        except QueryError as err:
            return _retry_or_fail(state["attempts"], str(err)), "retry", str(err)
        update = {
            "columns": result.columns,
            "rows": result.rows,
            "job_id": result.job_id,
            "bytes_processed": result.bytes_processed,
            "cache_hit": result.cache_hit,
        }
        cache = ", BigQuery cache hit" if result.cache_hit else ""
        return update, "ok", f"{len(result.rows)} rows, job {result.job_id}{cache}"

    def facts_node(state: AgentState) -> NodeResult:
        facts = compute_facts(state["columns"], state["rows"])
        return {"facts": facts}, "ok", f"{len(facts)} facts computed"

    def chart_node(state: AgentState) -> NodeResult:
        chart = choose_chart(state["columns"], state["rows"])
        return {"chart": chart}, "ok", chart["type"]

    def explain_node(state: AgentState) -> NodeResult:
        outcome = explain(deps.llm, settings.model_lite, state["question"], state["facts"], settings.prompt_version)
        usage = {
            "calls": len(outcome.calls),
            "input_tokens": sum(c.input_tokens for c in outcome.calls),
            "output_tokens": sum(c.output_tokens for c in outcome.calls),
        }
        detail = f"insight from {outcome.source}"
        if outcome.rejected:
            detail += f"; rejected ungrounded numbers: {', '.join(outcome.rejected)}"
        update = {"insight": outcome.insight, "insight_source": outcome.source, "llm": usage, "status": "answered"}
        return update, "ok", detail

    def route(ok_target: str) -> Callable[[AgentState], str]:
        def decide(state: AgentState) -> str:
            if state.get("status") != "running":
                return END
            if state.get("last_error"):
                return "write_sql"
            return ok_target

        return decide

    graph = StateGraph(AgentState)
    graph.add_node("prefilter", _timed("prefilter", prefilter_node))
    graph.add_node("write_sql", _timed("write_sql", write_sql_node))
    graph.add_node("validate_sql", _timed("validate_sql", validate_node))
    graph.add_node("dry_run", _timed("dry_run", dry_run_node))
    graph.add_node("execute", _timed("execute", execute_node))
    graph.add_node("compute_facts", _timed("compute_facts", facts_node))
    graph.add_node("chart", _timed("chart", chart_node))
    graph.add_node("explain", _timed("explain", explain_node))

    graph.add_edge(START, "prefilter")
    graph.add_conditional_edges("prefilter", route("write_sql"), ["write_sql", END])
    graph.add_conditional_edges("write_sql", route("validate_sql"), ["validate_sql", "write_sql", END])
    graph.add_conditional_edges("validate_sql", route("dry_run"), ["dry_run", "write_sql", END])
    graph.add_conditional_edges("dry_run", route("execute"), ["execute", "write_sql", END])
    graph.add_conditional_edges("execute", route("compute_facts"), ["compute_facts", "write_sql", END])
    graph.add_edge("compute_facts", "chart")
    graph.add_edge("chart", "explain")
    graph.add_edge("explain", END)
    return graph.compile()


class Agent:
    def __init__(self, deps: Dependencies):
        self._deps = deps
        self._graph = build_graph(deps)

    def ask(self, question: str, request_id: str) -> dict:
        start = time.perf_counter()
        initial: AgentState = {
            "request_id": request_id,
            "question": question,
            "attempts": 0,
            "status": "running",
            "trace": [],
            "llm": {"calls": 0, "input_tokens": 0, "output_tokens": 0},
        }
        try:
            state = self._graph.invoke(initial)
        except Exception:
            log.exception("agent crashed", extra={"request_id": request_id})
            state = {**initial, "status": "failed", "code": "INTERNAL", "message": "Unexpected error."}
        return to_response(state, self._deps.settings, round((time.perf_counter() - start) * 1000))


def to_response(state: AgentState, settings: Settings, latency_ms: int) -> dict:
    answered = state.get("status") == "answered"
    rows = state.get("rows") or []
    llm = state.get("llm") or {}
    return {
        "status": state.get("status"),
        "code": state.get("code"),
        "message": state.get("message"),
        "answer": {
            "insight": state.get("insight"),
            "facts": state.get("facts") or [],
            "assumptions": state.get("assumptions") or [],
            "insightSource": state.get("insight_source"),
        }
        if answered
        else None,
        "data": {
            "columns": state.get("columns") or [],
            "rows": rows,
            "rowCount": len(rows),
            "truncated": len(rows) >= MAX_ROWS,
        }
        if answered
        else None,
        "chart": state.get("chart") if answered else None,
        "sql": state.get("sql"),
        "jobId": state.get("job_id"),
        "trace": state.get("trace") or [],
        "metrics": {
            "latencyMs": latency_ms,
            "bytesEstimate": state.get("bytes_estimate"),
            "bytesProcessed": state.get("bytes_processed") or 0,
            "bigqueryCacheHit": bool(state.get("cache_hit")),
            "attempts": state.get("attempts", 0),
            "llmCalls": llm.get("calls", 0),
            "inputTokens": llm.get("input_tokens", 0),
            "outputTokens": llm.get("output_tokens", 0),
        },
        "model": state.get("model") or settings.model_sql,
        "promptVersion": settings.prompt_version,
    }
