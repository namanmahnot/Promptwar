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


@dataclass(frozen=True)
class Settings:
    gcp_project: str | None
    model_sql: str
    model_lite: str
    max_bytes: int
    prompt_version: str
    internal_key: str | None
    environment: str

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        gcp_project=os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT"),
        model_sql=os.getenv("GEMINI_MODEL_SQL", "gemini-3.5-flash"),
        model_lite=os.getenv("GEMINI_MODEL_LITE", "gemini-3.5-flash-lite"),
        max_bytes=int(os.getenv("BQ_MAX_BYTES", "1000000000")),
        prompt_version=os.getenv("PROMPT_VERSION", "v1"),
        internal_key=os.getenv("INTERNAL_API_KEY") or None,
        environment=os.getenv("APP_ENV", "production"),
    )
