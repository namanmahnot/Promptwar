"""HTTP security: Firebase token verification, per-user rate limits, body size cap, headers."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from app.config import MAX_BODY_BYTES, RATE_LIMIT_PER_DAY, RATE_LIMIT_PER_MINUTE

TokenVerifier = Callable[[str], dict]

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' https://apis.google.com https://www.gstatic.com; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.googleusercontent.com; "
        "connect-src 'self' https://*.googleapis.com; frame-src https://*.firebaseapp.com https://accounts.google.com; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cross-Origin-Opener-Policy": "same-origin-allow-popups",  # Google sign-in popup
}

DEV_USER = {"uid": "dev-user", "email": "dev@localhost", "name": "Local developer"}
DEV_TOKEN = "dev"  # noqa: S105 — accepted only when APP_ENV=development and AUTH_DEV_BYPASS=true


def firebase_verifier(project: str | None, credentials=None, dev_bypass: bool = False) -> TokenVerifier:
    """Verifies Firebase ID tokens (signature, expiry, audience = our project)."""
    import firebase_admin
    from firebase_admin import auth

    options = {"projectId": project} if project else None
    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(credentials, options=options)

    def verify(token: str) -> dict:
        if dev_bypass and token == DEV_TOKEN:
            return DEV_USER
        return auth.verify_id_token(token, app=app)

    return verify


class RateLimiter:
    """Sliding-window limits per user: 10/minute and 100/day (in memory, per instance)."""

    def __init__(self, per_minute: int = RATE_LIMIT_PER_MINUTE, per_day: int = RATE_LIMIT_PER_DAY,
                 clock: Callable[[], float] = time.monotonic):
        self._windows = ((60.0, per_minute), (86_400.0, per_day))
        self._hits: dict[str, deque[float]] = {}
        self._clock = clock
        self._lock = threading.Lock()

    def check(self, key: str) -> int | None:
        """Record a hit and return None, or return seconds to wait if a limit is exceeded."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= 86_400.0:
                hits.popleft()
            for window, limit in self._windows:
                recent = [t for t in hits if now - t < window]
                if len(recent) >= limit:
                    return max(1, int(window - (now - recent[0])) + 1)
            hits.append(now)
            return None


class BodySizeLimit:
    """ASGI middleware: rejects bodies over MAX_BODY_BYTES, even without a Content-Length header."""

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            return await _too_large(send)

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await _too_large(send)


class _BodyTooLarge(Exception):
    pass


async def _too_large(send) -> None:
    body = b'{"status":"error","code":"PAYLOAD_TOO_LARGE","message":"The request body is too large."}'
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
