"""Every rule in docs/03 'SQL validator rules' has at least one passing and one failing case."""

import pytest

from app.nodes.validate_sql import validate_sql

T = "`bigquery-public-data.thelook_ecommerce"
ORDERS = f"{T}.orders`"
ITEMS = f"{T}.order_items`"
PRODUCTS = f"{T}.products`"
USERS = f"{T}.users`"
EVENTS = f"{T}.events`"
DCS = f"{T}.distribution_centers`"


def ok(sql: str):
    result = validate_sql(sql)
    assert result.ok, result.violations
    return result


def blocked(sql: str, fragment: str = ""):
    result = validate_sql(sql)
    assert not result.ok, f"expected rejection: {sql}"
    assert result.violations
    if fragment:
        assert fragment.lower() in " ".join(result.violations).lower(), result.violations
    return result


# Rule 1 — exactly one statement
def test_plain_select_passes():
    result = ok(f"SELECT status, COUNT(*) AS n FROM {ORDERS} GROUP BY status")
    assert "1 statement" in result.checks


def test_two_statements_fail():
    blocked(f"SELECT 1 FROM {ORDERS}; SELECT 2 FROM {ORDERS}", "exactly 1 statement")


def test_trailing_semicolon_is_one_statement():
    ok(f"SELECT order_id FROM {ORDERS};")


# Rule 2 — root must be a query
def test_cte_passes():
    ok(
        f"WITH rev AS (SELECT product_id, SUM(sale_price) AS r FROM {ITEMS} GROUP BY 1) "
        "SELECT product_id, r FROM rev ORDER BY r DESC"
    )


def test_union_of_selects_passes():
    ok(f"SELECT status FROM {ORDERS} UNION ALL SELECT status FROM {ITEMS}")


@pytest.mark.parametrize(
    "sql",
    [
        f"DROP TABLE {ORDERS}",
        f"DELETE FROM {ITEMS} WHERE 1=1",
        f"INSERT INTO {ORDERS} SELECT * FROM {ORDERS}",
        f"UPDATE {ORDERS} SET status = 'x' WHERE TRUE",
        f"CREATE TABLE x AS SELECT * FROM {ORDERS}",
        "GRANT `roles/bigquery.dataViewer` ON TABLE x TO 'user:a@b.com'",
        "DECLARE x INT64 DEFAULT 1",
        "EXECUTE IMMEDIATE 'DROP TABLE x'",
        f"EXPORT DATA OPTIONS(uri='gs://b/*.csv') AS SELECT * FROM {ORDERS}",
        f"MERGE {ORDERS} t USING {ORDERS} s ON t.order_id = s.order_id WHEN MATCHED THEN DELETE",
    ],
)
def test_write_ddl_and_scripting_fail(sql):
    result = blocked(sql)
    assert result.retryable is False


# Rule 3 — comments cannot hide a second statement
def test_statement_hidden_after_comment_is_handled_by_parser():
    result = ok(f"SELECT order_id FROM {ORDERS} -- ;DROP TABLE x")
    assert "DROP" not in result.sql.upper()


def test_statement_after_block_comment_fails():
    blocked(f"SELECT order_id FROM {ORDERS} /* hi */; DROP TABLE {ORDERS}", "exactly 1 statement")


# Rule 4 — table allowlist
def test_table_outside_allowlist_fails():
    blocked("SELECT name FROM `bigquery-public-data.usa_names.usa_1910_current`", "outside the allowed dataset")


def test_unqualified_table_fails():
    blocked("SELECT order_id FROM orders", "not fully qualified")


def test_unknown_table_in_dataset_fails():
    blocked(f"SELECT * FROM {T}.secret_table`", "not in the allowlist")


def test_information_schema_fails():
    blocked(f"SELECT table_name FROM {T}.INFORMATION_SCHEMA.TABLES`", "INFORMATION_SCHEMA")


def test_region_information_schema_fails():
    blocked("SELECT * FROM `region-us`.INFORMATION_SCHEMA.JOBS", "INFORMATION_SCHEMA")


def test_table_inside_subquery_is_checked():
    blocked(f"SELECT x FROM (SELECT name AS x FROM `other-project.ds.t`) JOIN {ORDERS} o ON TRUE")


# Rule 5 — PII column denylist
def test_users_email_in_where_fails():
    blocked(f"SELECT COUNT(*) FROM {USERS} u WHERE u.email LIKE '%@gmail.com'", "users.email")


def test_users_email_in_select_fails():
    blocked(f"SELECT email FROM {USERS}", "users.email")


def test_pii_in_join_condition_fails():
    blocked(
        f"SELECT COUNT(*) FROM {USERS} u JOIN {EVENTS} e ON u.postal_code = e.postal_code",
        "users.postal_code",
    )


def test_pii_in_group_by_fails():
    blocked(f"SELECT COUNT(*) FROM {USERS} GROUP BY last_name", "users.last_name")


def test_latitude_via_alias_fails():
    blocked(
        f"SELECT state, AVG(cust.latitude) FROM {USERS} AS cust GROUP BY state",
        "users.latitude",
    )


def test_events_ip_address_fails():
    blocked(f"SELECT ip_address FROM {EVENTS}", "events.ip_address")


def test_pii_inside_cte_fails():
    blocked(f"WITH x AS (SELECT email FROM {USERS}) SELECT COUNT(*) FROM x", "users.email")


def test_safe_users_columns_pass():
    ok(f"SELECT country, COUNT(*) AS users FROM {USERS} GROUP BY country")


def test_distribution_center_latitude_is_not_pii():
    ok(f"SELECT name, latitude, longitude FROM {DCS}")


def test_whole_row_struct_of_users_fails():
    blocked(f"SELECT TO_JSON_STRING(u) FROM {USERS} u", "whole-row")


def test_pii_column_name_in_string_literal_passes():
    ok(f"SELECT traffic_source FROM {USERS} WHERE traffic_source != 'email'")


# Rule 6 — SELECT * over users / events
def test_select_star_from_users_fails():
    blocked(f"SELECT * FROM {USERS}", "SELECT *")


def test_qualified_star_from_users_fails():
    blocked(f"SELECT u.* FROM {USERS} u JOIN {ORDERS} o ON o.user_id = u.id", "SELECT *")


def test_select_star_from_events_fails():
    blocked(f"SELECT * FROM {EVENTS} LIMIT 5", "SELECT *")


def test_select_star_from_orders_passes():
    ok(f"SELECT * FROM {ORDERS}")


def test_count_star_over_users_passes():
    ok(f"SELECT COUNT(*) AS n FROM {USERS}")


# Rule 7 — function denylist
def test_external_query_fails():
    blocked("SELECT * FROM EXTERNAL_QUERY('conn', 'SELECT 1')")


def test_session_user_fails():
    blocked(f"SELECT SESSION_USER() AS who FROM {ORDERS}", "SESSION_USER")


def test_ml_functions_fail():
    blocked(f"SELECT * FROM ML.PREDICT(MODEL `p.d.m`, (SELECT * FROM {ORDERS}))")


def test_function_name_inside_string_passes():
    ok(f"SELECT COUNT(*) FROM {ORDERS} WHERE status = 'EXTERNAL_QUERY'")


# Cartesian joins (cost control, attack A6)
def test_cross_join_fails():
    blocked(f"SELECT COUNT(*) FROM {ORDERS} CROSS JOIN {ITEMS}", "CROSS JOIN")


def test_comma_join_fails():
    # sqlglot normalises a comma join to a CROSS JOIN; either message is a rejection.
    blocked(f"SELECT COUNT(*) FROM {ORDERS}, {ITEMS}", "join")


def test_join_without_condition_fails():
    blocked(f"SELECT COUNT(*) FROM {ORDERS} o JOIN {ITEMS} oi", "join")


def test_inner_join_with_on_passes():
    ok(
        f"SELECT p.category, SUM(oi.sale_price) AS revenue FROM {ITEMS} oi "
        f"JOIN {PRODUCTS} p ON oi.product_id = p.id GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
    )


def test_join_unnest_passes():
    ok(f"SELECT o.order_id, x FROM {ORDERS} o, UNNEST([1, 2]) AS x")


# Rule 8 — LIMIT enforcement
def test_missing_limit_gets_limit_1000():
    result = ok(f"SELECT order_id FROM {ORDERS}")
    assert result.sql.rstrip().endswith("LIMIT 1000")
    assert "LIMIT 1000 added" in result.checks


def test_large_limit_is_lowered():
    result = ok(f"SELECT order_id FROM {ORDERS} LIMIT 50000")
    assert result.sql.rstrip().endswith("LIMIT 1000")
    assert "50000" not in result.sql


def test_small_limit_is_kept():
    result = ok(f"SELECT order_id FROM {ORDERS} LIMIT 5")
    assert result.sql.rstrip().endswith("LIMIT 5")


def test_union_gets_outer_limit():
    result = ok(f"SELECT status FROM {ORDERS} UNION ALL SELECT status FROM {ITEMS}")
    assert result.sql.rstrip().endswith("LIMIT 1000")


# Parse errors are retryable; safety violations are not
def test_garbage_is_retryable_parse_error():
    result = blocked("SELEC order_id FROM WHERE")
    assert result.retryable is True


def test_empty_sql_is_rejected():
    assert validate_sql("   ").ok is False


def test_safety_violation_is_not_retryable():
    assert validate_sql(f"SELECT email FROM {USERS}").retryable is False
