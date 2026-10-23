"""Rule-based chart choice from column types. The LLM never picks the chart."""

from __future__ import annotations

from app.columns import classify

MAX_BAR_CATEGORIES = 20


def choose_chart(columns: list[dict], rows: list[dict]) -> dict:
    roles = classify(columns)
    if len(rows) < 2 or not roles.measures or not roles.dimensions:
        return {"type": "table"}

    x = roles.dimensions[0]["name"]
    y = roles.measures[0]["name"]
    if roles.time_dimension is not None:
        return {"type": "line", "x": x, "y": y}
    if len(rows) <= MAX_BAR_CATEGORIES:
        return {"type": "bar", "x": x, "y": y}
    return {"type": "table"}
