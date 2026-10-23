"""Classify result columns into dimensions and measures from their BigQuery types."""

from __future__ import annotations

import re
from dataclasses import dataclass

NUMERIC_TYPES = frozenset({"INT64", "FLOAT64", "NUMERIC", "BIGNUMERIC"})
TEMPORAL_TYPES = frozenset({"DATE", "DATETIME", "TIMESTAMP", "TIME"})

_TIME_NAME = re.compile(r"(^|_)(year|month|week|day|date|quarter|period)(_|$)", re.IGNORECASE)
_ID_NAME = re.compile(r"(^id$|_id$)", re.IGNORECASE)


@dataclass(frozen=True)
class Roles:
    dimensions: list[dict]
    measures: list[dict]

    @property
    def time_dimension(self) -> dict | None:
        first = self.dimensions[0] if self.dimensions else None
        return first if first is not None and is_temporal(first) else None


def is_temporal(column: dict) -> bool:
    return column["type"] in TEMPORAL_TYPES or bool(_TIME_NAME.search(column["name"]))


def classify(columns: list[dict]) -> Roles:
    dimensions: list[dict] = []
    measures: list[dict] = []
    for column in columns:
        is_measure = (
            column["type"] in NUMERIC_TYPES
            and not _ID_NAME.search(column["name"])
            and not (column["type"] == "INT64" and is_temporal(column))
        )
        (measures if is_measure else dimensions).append(column)
    return Roles(dimensions, measures)


def humanize(name: str) -> str:
    return name.replace("_", " ").strip()
