"""Gemini access via google-genai, with timeouts, one retry and a Flash-Lite fallback."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)

TIMEOUT_MS = 20_000
RETRY_BACKOFF_S = 1.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LlmUnavailable(Exception):
    """Gemini quota exhausted or unreachable after retry and fallback."""


@dataclass(frozen=True)
class LlmResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class Llm(Protocol):
    def generate(self, prompt: str, *, model: str, json_schema: dict | None = None) -> LlmResult: ...


class GeminiLlm:
    def __init__(self, fallback_model: str):
        from google import genai
        from google.genai import types

        self._types = types
        # Reads GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI + project/location for Vertex AI.
        self._client = genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        self._fallback_model = fallback_model

    def generate(self, prompt: str, *, model: str, json_schema: dict | None = None) -> LlmResult:
        attempts = [model, model] + ([self._fallback_model] if self._fallback_model != model else [])
        last_error: Exception | None = None
        for index, attempt_model in enumerate(attempts):
            if index:
                time.sleep(RETRY_BACKOFF_S)
            try:
                return self._call(prompt, attempt_model, json_schema)
            except Exception as err:  # noqa: BLE001 — classified below
                if not _is_retryable(err):
                    raise LlmUnavailable(_describe(err)) from err
                last_error = err
                log.warning("gemini call failed", extra={"model": attempt_model, "error": _describe(err)})
        raise LlmUnavailable(_describe(last_error)) from last_error

    def _call(self, prompt: str, model: str, json_schema: dict | None) -> LlmResult:
        config = self._types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json" if json_schema else "text/plain",
            response_json_schema=json_schema,
        )
        response = self._client.models.generate_content(model=model, contents=prompt, config=config)
        usage = response.usage_metadata
        return LlmResult(
            text=response.text or "",
            model=model,
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
        )


def _is_retryable(err: Exception) -> bool:
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    if isinstance(code, int):
        return code in _RETRYABLE_STATUS
    return isinstance(err, TimeoutError | ConnectionError) or "timeout" in type(err).__name__.lower()


def _describe(err: Exception | None) -> str:
    if err is None:
        return "unknown error"
    code = getattr(err, "code", None)
    return f"{type(err).__name__}({code})" if code else type(err).__name__
