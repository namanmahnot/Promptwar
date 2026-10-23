"""Builds the compact schema the model sees, once at startup, with PII columns removed."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from app.bq import Warehouse
from app.config import ALLOWED_TABLES, DATASET, PII_COLUMNS

log = logging.getLogger(__name__)

JOIN_KEYS = (
    "order_items.order_id = orders.order_id",
    "order_items.product_id = products.id",
    "order_items.user_id = users.id",
    "orders.user_id = users.id",
    "order_items.inventory_item_id = inventory_items.id",
    "inventory_items.product_id = products.id",
    "products.distribution_center_id = distribution_centers.id",
    "events.user_id = users.id",
)


class SchemaCache:
    def __init__(self) -> None:
        self.ddl: str | None = None

    @property
    def loaded(self) -> bool:
        return self.ddl is not None

    def load(self, warehouse: Warehouse) -> None:
        names = sorted(ALLOWED_TABLES)
        # Seven independent metadata lookups: fetch them in parallel to keep cold starts short.
        with ThreadPoolExecutor(max_workers=len(names)) as pool:
            schemas = pool.map(lambda name: warehouse.table_schema(f"{DATASET}.{name}"), names)
        tables = dict(zip(names, schemas, strict=True))
        self.ddl = build_ddl(tables)
        log.info("schema cache loaded", extra={"tables": len(tables)})


def build_ddl(tables: dict[str, list[dict]]) -> str:
    lines = []
    for name, columns in tables.items():
        hidden = PII_COLUMNS.get(name, frozenset())
        visible = [c for c in columns if c["name"].lower() not in hidden and c["type"] != "GEOGRAPHY"]
        cols = ", ".join(f"{c['name']} {c['type']}" for c in visible)
        lines.append(f"`{DATASET}.{name}` ({cols})")
    lines.append("Join keys: " + "; ".join(JOIN_KEYS))
    return "\n".join(lines)
