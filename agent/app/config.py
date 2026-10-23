"""Runtime settings and the fixed data-access policy.

The policy constants (allowlist, PII denylist) are code, not configuration, on purpose:
they are the security boundary and must not be loosened by an environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DATASET_PROJECT = "bigquery-public-data"
DATASET_NAME = "thelook_ecommerce"
DATASET = f"{DATASET_PROJECT}.{DATASET_NAME}"

ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "orders",
        "order_items",
        "products",
        "users",
        "inventory_items",
        "distribution_centers",
        "events",
    }
)

# Columns that identify or locate a person. Never shown to the model, never allowed in SQL.
PII_COLUMNS: dict[str, frozenset[str]] = {
    "users": frozenset(
        {
            "email",
            "first_name",
            "last_name",
            "street_address",
            "postal_code",
            "latitude",
            "longitude",
            "user_geom",
        }
    ),
    "events": frozenset({"ip_address"}),
}

MAX_ROWS = 1000
MAX_SQL_ATTEMPTS = 3  # first try + 2 retries
QUESTION_MIN_CHARS = 3
QUESTION_MAX_CHARS = 500


RATE_LIMIT_PER_MINUTE = 10
RATE_LIMIT_PER_DAY = 100
MAX_BODY_BYTES = 10 * 1024
CACHE_TTL_SECONDS = 6 * 60 * 60
ROWS_RETURNED = 200
HISTORY_LIMIT = 20


@dataclass(frozen=True)
class Settings:
    gcp_project: str | None
    model_sql: str
    model_lite: str
    max_bytes: int
    prompt_version: str
    environment: str
    auth_dev_bypass: bool = False
    store: str = "memory"  # "firestore" in production
    cors_origins: tuple[str, ...] = ()
    web_dist: str | None = None

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    environment = os.getenv("APP_ENV", "production")
    auth_dev_bypass = os.getenv("AUTH_DEV_BYPASS", "false").lower() == "true"
    if auth_dev_bypass and environment != "development":
        raise RuntimeError("AUTH_DEV_BYPASS is only allowed when APP_ENV=development")
    return Settings(
        gcp_project=os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT"),
        model_sql=os.getenv("GEMINI_MODEL_SQL", "gemini-3.5-flash"),
        model_lite=os.getenv("GEMINI_MODEL_LITE", "gemini-3.5-flash-lite"),
        max_bytes=int(os.getenv("BQ_MAX_BYTES", "1000000000")),
        prompt_version=os.getenv("PROMPT_VERSION", "v1"),
        environment=environment,
        auth_dev_bypass=auth_dev_bypass,
        store=os.getenv("STORE", "memory" if environment == "development" else "firestore"),
        cors_origins=tuple(o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()),
        web_dist=os.getenv("WEB_DIST") or None,
    )
