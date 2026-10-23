"""InsightPilot API: one FastAPI service that authenticates users, runs the agent and serves the web app.

Request path for POST /api/ask (docs/03 "Defense layers"):
  body cap → Firebase token → pydantic validation → rate limit → answer cache → agent → audit → response
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.config import (
    CACHE_TTL_SECONDS,
    HISTORY_LIMIT,
    QUESTION_MAX_CHARS,
    QUESTION_MIN_CHARS,
    ROWS_RETURNED,
    Settings,
    get_settings,
)
from app.evaluation import EVAL_DIR
from app.graph import Agent, Dependencies
from app.logging_config import configure_logging
from app.schema_cache import SchemaCache
from app.security import SECURITY_HEADERS, BodySizeLimit, RateLimiter, TokenVerifier
from app.store import Store, cache_key

log = logging.getLogger(__name__)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BEARER = re.compile(r"^Bearer ([A-Za-z0-9._-]+)$")
_FAILURE_HTTP = {"SQL_FAILED": 502, "LLM_UNAVAILABLE": 503}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after


class AskBody(BaseModel):
    model_config = {"extra": "forbid"}

    question: str = Field(min_length=QUESTION_MIN_CHARS, max_length=QUESTION_MAX_CHARS)

    @field_validator("question", mode="before")
    @classmethod
    def clean(cls, value):
        if not isinstance(value, str):
            raise ValueError("question must be a string")
        return " ".join(_CONTROL_CHARS.sub(" ", value).split())


@dataclass
class Services:
    deps: Dependencies
    agent: Agent
    store: Store
    verify_token: TokenVerifier
    limiter: RateLimiter


def services_of(request: Request) -> Services:
    return request.app.state.services


def current_user(request: Request, authorization: Annotated[str | None, Header()] = None) -> dict:
    """Firebase ID token on every /api route; the uid only ever comes from the verified token."""
    match = _BEARER.match(authorization or "")
    if not match:
        raise ApiError(401, "AUTH_REQUIRED", "Sign in to continue.")
    try:
        claims = services_of(request).verify_token(match.group(1))
    except Exception as err:
        raise ApiError(401, "AUTH_REQUIRED", "Your session is invalid or expired. Please sign in again.") from err
    request.state.uid = claims["uid"]
    return claims


User = Annotated[dict, Depends(current_user)]


def create_app(services: Services | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or (services.deps.settings if services else get_settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        app.state.services = services or _production_services(settings)
        yield

    app = FastAPI(
        title="InsightPilot",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_dev else None,
    )
    if settings.cors_origins:  # only when the web app is hosted on another origin (e.g. Firebase Hosting)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
            expose_headers=["X-Request-Id", "Retry-After"],
            max_age=600,
        )
    app.add_middleware(BodySizeLimit)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        request.state.uid = None
        start = time.perf_counter()
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        response.headers["X-Request-Id"] = request.state.request_id
        log.info(
            "request",
            extra={
                "request_id": request.state.request_id,
                "uid": request.state.uid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - start) * 1000),
            },
        )
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return _error(request, exc.status, exc.code, exc.message, headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        return _error(request, 400, "VALIDATION_ERROR", first.get("msg", "The request is invalid."))

    @app.get("/healthz")
    def healthz(request: Request) -> dict:
        return {"ok": True, "schemaLoaded": services_of(request).deps.schema.loaded}

    @app.post("/api/ask")
    def ask(body: AskBody, request: Request, user: User):
        svc = services_of(request)
        uid, request_id = user["uid"], request.state.request_id
        wait = svc.limiter.check(uid)
        if wait:
            raise ApiError(429, "RATE_LIMITED", "Too many questions. Please wait and try again.", retry_after=wait)
        if not svc.deps.schema.loaded:
            raise ApiError(503, "SCHEMA_UNAVAILABLE", "The data catalogue is still loading. Please retry shortly.")

        start = time.perf_counter()
        key = cache_key(body.question, svc.deps.settings.model_sql, svc.deps.settings.prompt_version)
        cached = _safely("cache read", request_id, lambda: svc.store.get_cached(key))
        if cached:
            response = _as_cache_hit(cached, body.question, request_id, start)
        else:
            result = svc.agent.ask(body.question, request_id)
            response = _client_response(result, body.question, request_id)
            if response["status"] == "answered":
                _safely("cache write", request_id, lambda: svc.store.save_cached(key, response, CACHE_TTL_SECONDS))

        response["metrics"]["latencyMs"] = round((time.perf_counter() - start) * 1000)
        _safely("audit write", request_id, lambda: svc.store.save_query(_audit_record(response, uid)))
        log.info(
            "ask",
            extra={
                "request_id": request_id,
                "uid": uid,
                "status": response["status"],
                "code": response["code"],
                "ms": response["metrics"]["latencyMs"],
                "bytes": response["metrics"]["bytesProcessed"],
                "model": response["model"],
            },
        )
        return JSONResponse(jsonable_encoder(response), status_code=_http_status(response))

    @app.get("/api/history")
    def history(request: Request, user: User) -> dict:
        items = services_of(request).store.list_history(user["uid"], HISTORY_LIMIT)
        fields = ("question", "status", "code", "latencyMs", "createdAt")
        rows = [{"queryId": q["requestId"], **{f: q.get(f) for f in fields}} for q in items]
        return jsonable_encoder({"items": rows})

    @app.get("/api/metrics/eval/latest")
    def eval_latest(request: Request, _user: User) -> dict:
        run = services_of(request).store.latest_eval() or _bundled_eval()
        return jsonable_encoder({"run": run})

    _mount_web(app, settings.web_dist)
    return app


def _error(request: Request, status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    body = {"status": "error", "code": code, "message": message, "requestId": request.state.request_id}
    return JSONResponse(body, status_code=status, headers=headers)


def _safely(label: str, request_id: str, fn):
    """Store failures are logged, never fatal: the user still gets the answer (docs/04 "Reliability")."""
    try:
        return fn()
    except Exception as err:
        log.error(f"{label} failed", extra={"request_id": request_id, "error": type(err).__name__})
        return None


def _client_response(result: dict, question: str, request_id: str) -> dict:
    data = result["data"]
    if data:
        data = {**data, "rows": data["rows"][:ROWS_RETURNED],
                "truncated": data["truncated"] or data["rowCount"] > ROWS_RETURNED}
    return {**result, "data": data, "queryId": request_id, "question": question, "cached": False}


def _as_cache_hit(cached: dict, question: str, request_id: str, start: float) -> dict:
    ms = round((time.perf_counter() - start) * 1000)
    return {
        **cached,
        "status": "cached",
        "cached": True,
        "queryId": request_id,
        "question": question,
        "trace": [{"step": "cache", "status": "ok", "ms": ms, "detail": f"answer reused from {cached['queryId']}"}],
        "metrics": {**cached["metrics"], "bytesProcessed": 0, "bytesEstimate": 0, "llmCalls": 0,
                    "inputTokens": 0, "outputTokens": 0, "attempts": 0},
    }


def _audit_record(response: dict, uid: str) -> dict:
    """One row per request. Result rows are deliberately not stored."""
    metrics, answer = response["metrics"], response.get("answer") or {}
    return {
        "requestId": response["queryId"],
        "uid": uid,
        "question": response["question"],
        "status": response["status"],
        "code": response["code"],
        "sql": response["sql"],
        "jobId": response["jobId"],
        "bytesProcessed": metrics["bytesProcessed"],
        "rowCount": (response.get("data") or {}).get("rowCount", 0),
        "insight": answer.get("insight"),
        "trace": response["trace"],
        "model": response["model"],
        "promptVersion": response["promptVersion"],
        "llm": {k: metrics[k] for k in ("llmCalls", "inputTokens", "outputTokens")},
        "latencyMs": metrics["latencyMs"],
    }


def _http_status(response: dict) -> int:
    if response["status"] in ("answered", "cached"):
        return 200
    if response["status"] == "blocked":
        return 422
    return _FAILURE_HTTP.get(response["code"], 500)


def _bundled_eval() -> dict | None:
    path = EVAL_DIR / "latest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _mount_web(app: FastAPI, web_dist: str | None) -> None:
    """Serve the built React app from the same origin, so no CORS is needed in production."""
    if not web_dist or not Path(web_dist, "index.html").exists():
        return
    root = Path(web_dist).resolve()
    if (root / "assets").exists():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"status": "error", "code": "NOT_FOUND", "message": "Not found."}, status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})


def _service_account_info() -> dict | None:
    """Service-account key JSON from GOOGLE_SERVICE_ACCOUNT_JSON; None means Application Default Credentials."""
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as err:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from err
    if info.get("type") != "service_account":
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON must be a service account key")
    return info


def _production_dependencies(settings: Settings | None = None) -> Dependencies:
    from app.bq import BigQueryWarehouse
    from app.llm import GeminiLlm

    settings = settings or get_settings()
    warehouse = BigQueryWarehouse(settings.gcp_project, settings.max_bytes, _service_account_info())
    schema = SchemaCache()
    try:
        schema.load(warehouse)
    except Exception:
        log.exception("schema cache failed to load; /api/ask will return 503")
    return Dependencies(settings=settings, llm=GeminiLlm(settings.model_lite), warehouse=warehouse, schema=schema)


def _production_services(settings: Settings) -> Services:
    from app.security import firebase_verifier
    from app.store import FirestoreStore, MemoryStore

    info = _service_account_info()
    project = settings.gcp_project or (info or {}).get("project_id")
    deps = _production_dependencies(settings)

    store_credentials = admin_credentials = None
    if info:
        from firebase_admin import credentials as admin_creds
        from google.oauth2 import service_account

        store_credentials = service_account.Credentials.from_service_account_info(info)
        admin_credentials = admin_creds.Certificate(info)

    store = FirestoreStore(project, store_credentials) if settings.store == "firestore" else MemoryStore()
    verifier = firebase_verifier(project, admin_credentials, dev_bypass=settings.auth_dev_bypass)
    return Services(deps=deps, agent=Agent(deps), store=store, verify_token=verifier, limiter=RateLimiter())


app = create_app()
