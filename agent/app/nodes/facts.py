"""compute_facts: every number the user sees in the insight is computed here, from BigQuery rows.

The LLM never does arithmetic; it may only restate these values.
"""

from __future__ import annotations

import math
import re
from typing import Any

from app.columns import classify, humanize

# Summing these across rows is meaningless (an average of averages, a sum of rates, ...).
_NON_ADDITIVE = re.compile(
    r"(avg|average|mean|median|rate|ratio|pct|percent|share|min|max|days|age|price|margin)", re.IGNORECASE
)


def compute_facts(columns: list[dict], rows: list[dict]) -> list[dict]:
    facts: list[dict] = [{"label": "Rows returned", "value": len(rows)}]
    if not rows:
        return facts

    roles = classify(columns)
    if len(rows) == 1:
        for column in columns:
            value = rows[0].get(column["name"])
            if value is not None:
                facts.append({"label": humanize(column["name"]), "value": _clean(value)})
        return facts

    if not roles.measures:
        return facts

    measure = roles.measures[0]["name"]
    dimension = roles.dimensions[0]["name"] if roles.dimensions else None
    points: list[tuple[Any, float]] = []
    for index, row in enumerate(rows):
        value = _to_number(row.get(measure))
        if value is not None:
            points.append((row.get(dimension) if dimension else index + 1, value))
    if not points:
        return facts

    m_label = humanize(measure)
    d_label = humanize(dimension) if dimension else "row"

    total = sum(value for _, value in points)
    additive = not _NON_ADDITIVE.search(measure)
    if additive:
        facts.append({"label": f"Total {m_label}", "value": _round(total)})

    if roles.time_dimension is not None:
        ordered = sorted(points, key=lambda p: str(p[0]))
        (first_label, first), (last_label, last) = ordered[0], ordered[-1]
        facts.append({"label": f"First {d_label}", "value": _clean(first_label)})
        facts.append({"label": f"{m_label} in first {d_label}", "value": _round(first)})
        facts.append({"label": f"Last {d_label}", "value": _clean(last_label)})
        facts.append({"label": f"{m_label} in last {d_label}", "value": _round(last)})
        if first != 0:
            change = (last - first) / abs(first) * 100
            facts.append({"label": f"Change in {m_label}, first to last (%)", "value": round(change, 1)})

    top_label, top = max(points, key=lambda p: p[1])
    bottom_label, bottom = min(points, key=lambda p: p[1])
    facts.append({"label": f"Highest {d_label}", "value": _clean(top_label)})
    facts.append({"label": f"Highest {m_label}", "value": _round(top)})
    facts.append({"label": f"Lowest {d_label}", "value": _clean(bottom_label)})
    facts.append({"label": f"Lowest {m_label}", "value": _round(bottom)})

    if additive and total > 0 and top >= 0:
        facts.append({"label": f"Highest {d_label} share of total (%)", "value": round(top / total * 100, 1)})
    return facts


def _to_number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return None if isinstance(value, float) and math.isnan(value) else float(value)
    return None


def _round(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(value, 2)


def _clean(value):
    if isinstance(value, float):
        return _round(value)
    return value
