"""Test doubles for the two external systems, so the full graph runs offline."""

from __future__ import annotations

import json

from app.bq import QueryError, QueryResult
from app.config import Settings
from app.graph import Agent, Dependencies
from app.llm import LlmResult, LlmUnavailable
from app.schema_cache import SchemaCache

T = "`bigquery-public-data.thelook_ecommerce"
GOOD_SQL = (
    f"SELECT p.category, ROUND(SUM(oi.sale_price), 2) AS revenue FROM {T}.order_items` oi "
    f"JOIN {T}.products` p ON oi.product_id = p.id WHERE oi.status = 'Complete' "
    "GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
)
CATEGORY_ROWS = [
    {"category": "Outerwear & Coats", "revenue": 1500.5},
    {"category": "Jeans", "revenue": 1200.0},
    {"category": "Sweaters", "revenue": 800.25},
]
CATEGORY_COLUMNS = [{"name": "category", "type": "STRING"}, {"name": "revenue", "type": "FLOAT64"}]


def plan(sql: str = GOOD_SQL, answerable: bool = True) -> str:
    return json.dumps({"answerable": answerable, "sql": sql, "tables": [], "assumptions": ["Completed items only."]})


class FakeLlm:
    """Returns scripted SQL-plan responses and narratives; records every prompt."""

    def __init__(self, sql_responses: list[str | Exception], narratives: list[str] | None = None):
        self.sql_responses = list(sql_responses)
        self.narratives = list(narratives or ["Outerwear & Coats led with 1,500.50 in revenue."])
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, model: str, json_schema: dict | None = None) -> LlmResult:
        self.prompts.append(prompt)
        queue = self.sql_responses if json_schema else self.narratives
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return LlmResult(text=item, model=model, input_tokens=100, output_tokens=20)


class FakeWarehouse:
    def __init__(self, *, dry_run_bytes: int = 10_000_000, execute_errors: list[str] | None = None,
                 rows: list[dict] | None = None, columns: list[dict] | None = None):
        self.dry_run_bytes = dry_run_bytes
        self.execute_errors = list(execute_errors or [])
        self.rows = CATEGORY_ROWS if rows is None else rows
        self.columns = columns or CATEGORY_COLUMNS
        self.executed: list[str] = []
        self.dry_runs: list[str] = []

    def dry_run(self, sql: str) -> int:
        self.dry_runs.append(sql)
        return self.dry_run_bytes

    def execute(self, sql: str) -> QueryResult:
        self.executed.append(sql)
        if self.execute_errors:
            raise QueryError(self.execute_errors.pop(0))
        return QueryResult(self.columns, self.rows, job_id="job_test_1", bytes_processed=12345, cache_hit=False)

    def table_schema(self, table: str) -> list[dict]:
        return [{"name": "id", "type": "INT64"}, {"name": "email", "type": "STRING"}]


def settings(**overrides) -> Settings:
    values = {
        "gcp_project": "test",
        "model_sql": "flash",
        "model_lite": "flash-lite",
        "max_bytes": 1_000_000_000,
        "prompt_version": "v1",
        "internal_key": None,
        "environment": "test",
    }
    values.update(overrides)
    return Settings(**values)


def make_agent(llm: FakeLlm, warehouse: FakeWarehouse | None = None, **setting_overrides):
    schema = SchemaCache()
    schema.ddl = "`bigquery-public-data.thelook_ecommerce.orders` (order_id INT64)"
    deps = Dependencies(
        settings=settings(**setting_overrides),
        llm=llm,
        warehouse=warehouse or FakeWarehouse(),
        schema=schema,
    )
    return Agent(deps), deps


__all__ = ["LlmUnavailable", "FakeLlm", "FakeWarehouse", "make_agent", "plan", "settings", "GOOD_SQL", "T"]
