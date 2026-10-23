"""FastAPI entry point for the private agent service."""

from __future__ import annotations

import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from app.config import get_settings
from app.graph import Agent, Dependencies
from app.logging_config import configure_logging
from app.schema_cache import SchemaCache
from app.schemas import AskRequest

log = logging.getLogger(__name__)


def create_app(deps: Dependencies | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        app.state.deps = deps or _production_dependencies()
        app.state.agent = Agent(app.state.deps)
        yield

    settings = deps.settings if deps else get_settings()
    app = FastAPI(
        title="InsightPilot agent",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_dev else None,
    )

    def require_internal_key(x_internal_key: Annotated[str | None, Header()] = None) -> None:
        """Defence in depth on top of Cloud Run IAM; enforced only when INTERNAL_API_KEY is set."""
        expected = settings.internal_key
        if expected and not hmac.compare_digest((x_internal_key or "").encode(), expected.encode()):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})

    @app.get("/healthz")
    def healthz(request: Request) -> dict:
        deps_ = request.app.state.deps
        return {"ok": True, "schemaLoaded": deps_.schema.loaded, "promptVersion": deps_.settings.prompt_version}

    @app.post("/v1/ask", dependencies=[Depends(require_internal_key)])
    def ask(body: AskRequest, request: Request) -> dict:
        if not request.app.state.deps.schema.loaded:
            raise HTTPException(status_code=503, detail={"code": "SCHEMA_UNAVAILABLE"})
        log.info("ask", extra={"requestId": body.requestId, "uid": body.uid})
        return request.app.state.agent.ask(body.question, body.requestId)

    @app.post("/v1/eval/run", dependencies=[Depends(require_internal_key)])
    def run_eval_endpoint(request: Request) -> dict:
        from app.evaluation import run_evaluation

        return run_evaluation(request.app.state.agent, request.app.state.deps)

    return app


def _production_dependencies() -> Dependencies:
    from app.bq import BigQueryWarehouse
    from app.llm import GeminiLlm

    settings = get_settings()
    warehouse = BigQueryWarehouse(settings.gcp_project, settings.max_bytes, _service_account_info())
    schema = SchemaCache()
    try:
        schema.load(warehouse)
    except Exception:
        log.exception("schema cache failed to load; /v1/ask will return 503")
    return Dependencies(settings=settings, llm=GeminiLlm(settings.model_lite), warehouse=warehouse, schema=schema)


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


app = create_app()
