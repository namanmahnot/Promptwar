from app.grounding import extract_numbers, format_value, template_insight, ungrounded_numbers

FACTS = [
    {"label": "Rows returned", "value": 5},
    {"label": "Total revenue", "value": 1234567.89},
    {"label": "Highest category", "value": "Outerwear & Coats"},
    {"label": "Highest revenue", "value": 401234.5},
    {"label": "Change in revenue, first to last (%)", "value": -12.3},
    {"label": "First month", "value": "2025-03-01"},
]


def test_exact_number_with_commas_is_grounded():
    assert ungrounded_numbers("Total revenue was $1,234,567.89.", FACTS, "q") == []


def test_number_rounded_to_written_precision_is_grounded():
    assert ungrounded_numbers("Revenue reached $1.2 million, led by $401K in coats.", FACTS, "q") == []


def test_percentage_and_sign_are_normalised():
    assert ungrounded_numbers("Revenue fell 12.3% over the period.", FACTS, "q") == []


def test_invented_number_is_rejected():
    assert ungrounded_numbers("Revenue grew 40% to $2,000,000.", FACTS, "q") == ["40%", "$2,000,000"]


def test_wrong_precision_is_rejected():
    assert ungrounded_numbers("Total revenue was 1,234,999.", FACTS, "q") == ["1,234,999"]


def test_numbers_from_the_question_are_allowed():
    assert ungrounded_numbers("Here are the top 5 categories.", FACTS, "Top 5 categories in the last 90 days") == []


def test_numbers_inside_fact_strings_are_allowed():
    assert ungrounded_numbers("Starting in March 2025, revenue declined.", FACTS, "q") == []


def test_ordinals_are_not_treated_as_quantities():
    assert extract_numbers("the 2nd quarter in 3D") == []


def test_template_is_grounded_by_construction():
    text = template_insight(FACTS)
    assert ungrounded_numbers(text, FACTS, "q") == []
    assert "Outerwear & Coats" in text


def test_template_for_empty_result():
    assert "no matching data" in template_insight([{"label": "Rows returned", "value": 0}])


def test_format_value():
    assert format_value(1234567.891) == "1,234,567.89"
    assert format_value(42.0) == "42"
    assert format_value("Jeans") == "Jeans"
