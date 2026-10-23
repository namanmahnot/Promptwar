"""write_sql: prompt construction and strict parsing of the model's structured output."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.prompts import load_prompt

SQL_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "sql": {"type": "string"},
        "tables": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answerable", "sql"],
}

MAX_ASSUMPTIONS = 3


@dataclass(frozen=True)
class SqlPlan:
    answerable: bool
    sql: str
    tables: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def build_prompt(
    question: str,
    schema_ddl: str,
    version: str,
    previous_sql: str | None = None,
    previous_error: str | None = None,
) -> str:
    error_block = ""
    if previous_error:
        error_block = (
            "\nYour previous attempt failed. Fix it.\n"
            f"Previous SQL: {previous_sql or '(none)'}\n"
            f"Error: {previous_error}\n"
        )
    return load_prompt("write_sql", version).format(
        schema_ddl=schema_ddl, previous_error_block=error_block, question=question
    )


def parse_plan(text: str) -> SqlPlan:
    """Parse model JSON. Raises ValueError on anything malformed so the graph can retry."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as err:
        raise ValueError(f"Model output was not valid JSON: {err.msg}") from err
    if not isinstance(data, dict) or not isinstance(data.get("answerable"), bool):
        raise ValueError("Model output is missing the boolean 'answerable' field.")

    sql = data.get("sql") or ""
    if not isinstance(sql, str):
        raise ValueError("Model output field 'sql' must be a string.")
    if data["answerable"] and not sql.strip():
        raise ValueError("Model said the question is answerable but returned no SQL.")

    return SqlPlan(
        answerable=data["answerable"],
        sql=sql.strip(),
        tables=[str(t) for t in data.get("tables") or []][:10],
        assumptions=[str(a)[:200] for a in data.get("assumptions") or []][:MAX_ASSUMPTIONS],
    )
