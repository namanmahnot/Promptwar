"""BigQuery access: dry run and capped execution. No other module talks to BigQuery."""

from __future__ import annotations

import datetime as dt
import decimal
from dataclasses import dataclass
from typing import Protocol

from app.config import MAX_ROWS

JOB_LABELS = {"app": "insightpilot"}
DRY_RUN_TIMEOUT_S = 10
EXECUTE_TIMEOUT_S = 30

_TYPE_ALIASES = {"INTEGER": "INT64", "FLOAT": "FLOAT64", "BOOLEAN": "BOOL", "RECORD": "STRUCT", "DECIMAL": "NUMERIC"}


class QueryError(Exception):
    """BigQuery rejected or failed the query; the message is safe to feed back to the model."""


@dataclass(frozen=True)
class QueryResult:
    columns: list[dict]
    rows: list[dict]
    job_id: str
    bytes_processed: int
    cache_hit: bool


class Warehouse(Protocol):
    def dry_run(self, sql: str) -> int: ...

    def execute(self, sql: str) -> QueryResult: ...

    def table_schema(self, table: str) -> list[dict]: ...


class BigQueryWarehouse:
    def __init__(self, project: str | None, max_bytes: int, service_account_info: dict | None = None):
        from google.cloud import bigquery

        credentials = None
        if service_account_info:
            # Hosts without Google workload identity get the key as an env var, never a committed file.
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=["https://www.googleapis.com/auth/bigquery"]
            )
            project = project or service_account_info.get("project_id")

        self._bq = bigquery
        self._client = bigquery.Client(project=project, credentials=credentials)
        self._max_bytes = max_bytes

    def dry_run(self, sql: str) -> int:
        from google.api_core import exceptions

        config = self._bq.QueryJobConfig(dry_run=True, use_query_cache=False, labels=JOB_LABELS)
        try:
            job = self._client.query(sql, job_config=config, timeout=DRY_RUN_TIMEOUT_S)
        except exceptions.GoogleAPICallError as err:
            raise QueryError(_message(err)) from err
        return int(job.total_bytes_processed or 0)

    def execute(self, sql: str) -> QueryResult:
        from google.api_core import exceptions

        config = self._bq.QueryJobConfig(
            maximum_bytes_billed=self._max_bytes,
            use_query_cache=True,
            labels=JOB_LABELS,
            job_timeout_ms=EXECUTE_TIMEOUT_S * 1000,
        )
        try:
            job = self._client.query(sql, job_config=config, timeout=EXECUTE_TIMEOUT_S)
            result = job.result(timeout=EXECUTE_TIMEOUT_S, max_results=MAX_ROWS)
        except exceptions.GoogleAPICallError as err:
            raise QueryError(_message(err)) from err
        except TimeoutError as err:
            raise QueryError("Query exceeded the 30 s time limit.") from err

        columns = [{"name": f.name, "type": _normalize_type(f.field_type)} for f in result.schema]
        rows = [{key: to_json_value(value) for key, value in row.items()} for row in result]
        return QueryResult(
            columns=columns,
            rows=rows,
            job_id=job.job_id,
            bytes_processed=int(job.total_bytes_processed or 0),
            cache_hit=bool(job.cache_hit),
        )

    def table_schema(self, table: str) -> list[dict]:
        ref = self._client.get_table(table, timeout=DRY_RUN_TIMEOUT_S)
        return [
            {"name": f.name, "type": _normalize_type(f.field_type), "description": f.description or ""}
            for f in ref.schema
        ]


def _normalize_type(field_type: str) -> str:
    upper = (field_type or "STRING").upper()
    return _TYPE_ALIASES.get(upper, upper)


def _message(err: Exception) -> str:
    message = getattr(err, "message", None) or str(err)
    return message.splitlines()[0][:500]


def to_json_value(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {k: to_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json_value(v) for v in value]
    return value
