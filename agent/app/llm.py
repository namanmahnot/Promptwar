"""Gemini access via google-genai, with timeouts, one retry and a Flash-Lite fallback."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)

TIMEOUT_MS = 20_000
RETRY_BACKOFF_S = 1.0
MAX_BACKOFF_S = 12.0  # cap so a retry still fits the gateway's 45 s budget
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_RETRY_DELAY = re.compile(r"retry_?[Dd]elay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s")


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
        self._cooldown_until: dict[str, float] = {}  # model -> monotonic time its quota resets

    def generate(self, prompt: str, *, model: str, json_schema: dict | None = None) -> LlmResult:
        # Retry the same model once after a short backoff, then switch straight to the cheaper
        # fallback (its own quota). A model whose quota won't reset within MAX_BACKOFF_S is skipped
        # entirely until then, so an exhausted daily quota costs one fast 429, not two long waits.
        attempts = [model, model] + ([self._fallback_model] if self._fallback_model != model else [])
        last_error: Exception | None = None
        previous: str | None = None
        for index, attempt_model in enumerate(attempts):
            if self._cooling_down(attempt_model):
                continue
            if attempt_model == previous and last_error is not None:
                time.sleep(_backoff_seconds(last_error, index))
            previous = attempt_model
            try:
                return self._call(prompt, attempt_model, json_schema)
            except Exception as err:  # noqa: BLE001 — classified below
                if not _is_retryable(err):
                    raise LlmUnavailable(_describe(err)) from err
                last_error = err
                delay = _retry_delay(err)
                if delay is not None and delay > MAX_BACKOFF_S:
                    self._cooldown_until[attempt_model] = time.monotonic() + delay
                log.warning("gemini call failed", extra={"model": attempt_model, "error": _describe(err)})
        raise LlmUnavailable(_describe(last_error)) from last_error

    def _cooling_down(self, model: str) -> bool:
        return time.monotonic() < self._cooldown_until.get(model, 0.0)

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


def _retry_delay(err: Exception | None) -> float | None:
    """The server's suggested wait (RetryInfo.retryDelay) on a 429, if it sent one."""
    match = _RETRY_DELAY.search(str(err)) if err is not None else None
    return float(match.group(1)) if match else None


def _backoff_seconds(err: Exception | None, attempt: int) -> float:
    """Honour the server's retryDelay on 429 when present; otherwise back off exponentially (1 s, 4 s)."""
    delay = _retry_delay(err)
    if delay is None:
        delay = RETRY_BACKOFF_S * 4 ** (attempt - 1)
    return min(delay, MAX_BACKOFF_S)


def _describe(err: Exception | None) -> str:
    if err is None:
        return "unknown error"
    code = getattr(err, "code", None)
    return f"{type(err).__name__}({code})" if code else type(err).__name__
