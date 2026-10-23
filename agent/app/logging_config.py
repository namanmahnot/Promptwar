"""One JSON line per log event on stdout; Cloud Logging parses ``severity`` automatically."""

from __future__ import annotations

import json
import logging
import re
import sys

_REDACT = re.compile(r"(key|token|secret|authorization|password)", re.IGNORECASE)
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"severity": record.levelname, "message": record.getMessage(), "logger": record.name}
        for key, value in vars(record).items():
            if key in _STANDARD or key.startswith("_"):
                continue
            payload[key] = "[redacted]" if _REDACT.search(key) else value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "google", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
