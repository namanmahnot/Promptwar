"""Deterministic SQL validator — the security boundary between the LLM and BigQuery.

Implements the rules in docs/03-security-integrity.md ("SQL validator rules") on the
sqlglot AST (dialect ``bigquery``), never on raw strings, so comments and quoting tricks
cannot hide a statement. Anything the validator cannot prove safe is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import TokenType

from app.config import ALLOWED_TABLES, DATASET_NAME, DATASET_PROJECT, MAX_ROWS, PII_COLUMNS

_DIALECT = "bigquery"

_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)

# Statement / scripting node types that must never appear anywhere in the tree.
_FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "AlterTable",
    "Grant",
    "Revoke",
    "Command",
    "Set",
    "Declare",
    "Execute",
    "Export",
    "LoadData",
    "Copy",
    "Use",
    "TruncateTable",
    "Transaction",
    "Commit",
    "Rollback",
)
_FORBIDDEN_NODES = tuple(
    getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES if hasattr(exp, name)
)

_DENIED_FUNCTIONS = frozenset({"EXTERNAL_QUERY", "SESSION_USER", "VECTOR_SEARCH"})
_DENIED_FUNCTION_NAMESPACES = frozenset({"ML", "AI"})
_PII_TABLES = frozenset(PII_COLUMNS)


@dataclass
class ValidationResult:
    ok: bool
    sql: str | None = None
    checks: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    # True only for parse errors: the model may try again. Safety violations are final.
    retryable: bool = False


def validate_sql(sql: str) -> ValidationResult:
    result = ValidationResult(ok=False)

    if not sql or not sql.strip():
        result.violations.append("Empty SQL.")
        result.retryable = True
        return result

    # Rule 7 runs on tokens: comments are already stripped and string literals are skipped.
    try:
        tokens = sqlglot.Dialect.get_or_raise(_DIALECT).tokenize(sql)
    except TokenError as err:
        result.violations.append(f"SQL could not be tokenized: {err}")
        result.retryable = True
        return result

    try:
        statements = [s for s in sqlglot.parse(sql, read=_DIALECT) if s is not None]
    except ParseError as err:
        result.violations.append(f"SQL could not be parsed: {_first_line(err)}")
        result.retryable = True
        return result

    # Rule 1: exactly one statement.
    if len(statements) != 1:
        result.violations.append(f"Expected exactly 1 statement, found {len(statements)}.")
        return result
    tree = statements[0]
    result.checks.append("1 statement")

    # Rule 2: the root is a read-only query.
    if not isinstance(tree, _ALLOWED_ROOTS):
        result.violations.append(f"Only SELECT queries are allowed (got {tree.key.upper()}).")
        return result

    # Rule 3: no write, DDL or scripting node anywhere.
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            result.violations.append(f"Forbidden statement type: {node.key.upper()}.")
            return result
    result.checks.append("read-only")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}

    # Rule 4: every table is allowlisted and fully qualified (CTE names excepted).
    alias_to_table: dict[str, str] = {}
    referenced: set[str] = set()
    for table in tree.find_all(exp.Table):
        violation = _check_table(table, cte_names)
        if violation:
            result.violations.append(violation)
            continue
        name = table.name.lower()
        if name in cte_names and not table.args.get("db"):
            continue
        referenced.add(name)
        alias_to_table[name] = name
        alias_to_table[table.alias_or_name.lower()] = name
    if result.violations:
        return result
    result.checks.append(f"{len(referenced)} allowlisted table(s)")

    # Rule 5 + 6: no PII columns, no whole-row access to PII tables.
    pii_violation = _check_pii(tree, referenced, alias_to_table)
    if pii_violation:
        result.violations.append(pii_violation)
        return result
    result.checks.append("no restricted columns")

    # Rule 7: function denylist.
    function_violation = _check_functions(tokens)
    if function_violation:
        result.violations.append(function_violation)
        return result
    result.checks.append("no restricted functions")

    # Extra cost rule: no cartesian joins (CROSS JOIN or a join without ON/USING).
    join_violation = _check_joins(tree)
    if join_violation:
        result.violations.append(join_violation)
        return result
    result.checks.append("no cartesian joins")

    # Rule 8: cap the outermost LIMIT.
    limit_note = _enforce_limit(tree)
    result.checks.append(limit_note)

    # Rule 9: return the rewritten SQL plus the checks that passed.
    result.ok = True
    result.sql = tree.sql(dialect=_DIALECT)
    return result


def _first_line(err: Exception) -> str:
    return str(err).strip().splitlines()[0] if str(err).strip() else type(err).__name__


def _check_table(table: exp.Table, cte_names: set[str]) -> str | None:
    parts = [p.lower() for p in (table.catalog, table.db, table.name) if p]
    if any("information_schema" in p for p in parts):
        return "INFORMATION_SCHEMA is not allowed."
    if not table.name:
        return "Table-valued expressions are not allowed."

    name = table.name.lower()
    catalog, db = table.catalog.lower(), table.db.lower()
    if not db and not catalog and name in cte_names:
        return None
    if catalog != DATASET_PROJECT or db != DATASET_NAME:
        shown = ".".join(parts)
        return f"Table `{shown}` is outside the allowed dataset or not fully qualified."
    if name not in ALLOWED_TABLES:
        return f"Table `{name}` is not in the allowlist."
    return None


def _check_pii(tree: exp.Expression, referenced: set[str], alias_to_table: dict[str, str]) -> str | None:
    pii_tables_used = referenced & _PII_TABLES
    if not pii_tables_used:
        return None

    pii_aliases = {alias for alias, table in alias_to_table.items() if table in _PII_TABLES}

    for column in tree.find_all(exp.Column):
        name = column.name.lower()
        qualifier = column.table.lower()

        # `SELECT u` or `TO_JSON_STRING(u)` returns the whole row as a STRUCT.
        if not qualifier and name in pii_aliases:
            return f"Whole-row access to `{alias_to_table[name]}` is not allowed."

        if isinstance(column.this, exp.Star):
            if qualifier in pii_aliases:
                return f"SELECT * over `{alias_to_table[qualifier]}` is not allowed."
            continue

        if qualifier:
            table = alias_to_table.get(qualifier)
            if table in PII_COLUMNS and name in PII_COLUMNS[table]:
                return f"Query references a restricted column ({table}.{name})."
        else:
            # Unqualified: reject if any PII table in the query owns a column with this name.
            for table in pii_tables_used:
                if name in PII_COLUMNS[table]:
                    return f"Query references a restricted column ({table}.{name})."

    for star in tree.find_all(exp.Star):
        if isinstance(star.parent, (exp.Count, exp.Column)):
            continue
        tables = ", ".join(sorted(pii_tables_used))
        return f"SELECT * is not allowed when the query reads {tables}."
    return None


def _check_functions(tokens: list) -> str | None:
    significant = [t for t in tokens if t.token_type != TokenType.STRING]
    for i, token in enumerate(significant):
        text = token.text.upper()
        if text in _DENIED_FUNCTIONS:
            return f"Function {text} is not allowed."
        nxt = significant[i + 1] if i + 1 < len(significant) else None
        if text in _DENIED_FUNCTION_NAMESPACES and nxt is not None and nxt.token_type == TokenType.DOT:
            return f"{text}.* functions are not allowed."
    return None


def _check_joins(tree: exp.Expression) -> str | None:
    for join in tree.find_all(exp.Join):
        if isinstance(join.this, exp.Unnest):
            continue
        if join.args.get("kind", "").upper() == "CROSS":
            return "CROSS JOIN is not allowed."
        if not join.args.get("on") and not join.args.get("using"):
            return "Joins must have an ON or USING condition."
    return None


def _enforce_limit(tree: exp.Expression) -> str:
    limit = tree.args.get("limit")
    current = None
    if isinstance(limit, exp.Limit):
        value = limit.args.get("expression")
        if isinstance(value, exp.Literal) and value.is_int:
            current = int(value.this)

    if current is not None and current <= MAX_ROWS:
        return f"LIMIT {current}"

    tree.set("limit", exp.Limit(expression=exp.Literal.number(MAX_ROWS)))
    if current is None and limit is None:
        return f"LIMIT {MAX_ROWS} added"
    return f"LIMIT lowered to {MAX_ROWS}"
