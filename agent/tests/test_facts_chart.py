from app.nodes.chart import choose_chart
from app.nodes.facts import compute_facts

CATEGORY = [{"name": "category", "type": "STRING"}, {"name": "revenue", "type": "FLOAT64"}]
MONTHLY = [{"name": "month", "type": "DATE"}, {"name": "orders", "type": "INT64"}]


def facts_dict(columns, rows):
    return {f["label"]: f["value"] for f in compute_facts(columns, rows)}


def test_ranking_facts():
    rows = [{"category": "A", "revenue": 300.0}, {"category": "B", "revenue": 100.0}]
    facts = facts_dict(CATEGORY, rows)
    assert facts["Rows returned"] == 2
    assert facts["Total revenue"] == 400
    assert facts["Highest category"] == "A"
    assert facts["Highest revenue"] == 300
    assert facts["Lowest category"] == "B"
    assert facts["Highest category share of total (%)"] == 75.0


def test_time_series_change_percent_uses_chronological_order():
    rows = [{"month": "2025-02-01", "orders": 150}, {"month": "2025-01-01", "orders": 100}]
    facts = facts_dict(MONTHLY, rows)
    assert facts["First month"] == "2025-01-01"
    assert facts["Last month"] == "2025-02-01"
    assert facts["Change in orders, first to last (%)"] == 50.0


def test_averages_are_not_summed():
    columns = [{"name": "country", "type": "STRING"}, {"name": "avg_order_value", "type": "FLOAT64"}]
    rows = [{"country": "A", "avg_order_value": 10.0}, {"country": "B", "avg_order_value": 20.0}]
    assert "Total avg order value" not in facts_dict(columns, rows)


def test_single_row_reports_each_value():
    columns = [{"name": "revenue", "type": "FLOAT64"}]
    assert facts_dict(columns, [{"revenue": 1234.567}])["revenue"] == 1234.57


def test_empty_result():
    assert compute_facts(CATEGORY, []) == [{"label": "Rows returned", "value": 0}]


def test_null_measures_are_ignored():
    rows = [{"category": "A", "revenue": None}, {"category": "B", "revenue": 5.0}]
    assert facts_dict(CATEGORY, rows)["Highest category"] == "B"


def test_bar_chart_for_categories():
    rows = [{"category": "A", "revenue": 1.0}, {"category": "B", "revenue": 2.0}]
    assert choose_chart(CATEGORY, rows) == {"type": "bar", "x": "category", "y": "revenue"}


def test_line_chart_for_dates():
    rows = [{"month": "2025-01-01", "orders": 1}, {"month": "2025-02-01", "orders": 2}]
    assert choose_chart(MONTHLY, rows) == {"type": "line", "x": "month", "y": "orders"}


def test_integer_year_is_a_time_dimension():
    columns = [{"name": "year", "type": "INT64"}, {"name": "users", "type": "INT64"}]
    rows = [{"year": 2024, "users": 1}, {"year": 2025, "users": 2}]
    assert choose_chart(columns, rows) == {"type": "line", "x": "year", "y": "users"}


def test_table_for_single_row_or_too_many_categories():
    assert choose_chart(CATEGORY, [{"category": "A", "revenue": 1.0}]) == {"type": "table"}
    many = [{"category": str(i), "revenue": float(i)} for i in range(21)]
    assert choose_chart(CATEGORY, many) == {"type": "table"}


def test_id_columns_are_not_measures():
    columns = [{"name": "product_id", "type": "INT64"}, {"name": "units", "type": "INT64"}]
    rows = [{"product_id": 1, "units": 5}, {"product_id": 2, "units": 3}]
    assert choose_chart(columns, rows) == {"type": "bar", "x": "product_id", "y": "units"}
