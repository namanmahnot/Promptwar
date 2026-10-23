import json

from fastapi.testclient import TestClient

from app.evaluation import EVAL_DIR, load_jsonl, results_match, run_evaluation
from app.main import create_app
from tests.fakes import GOOD_SQL, FakeLlm, FakeWarehouse, make_agent, plan

# --- result-set comparison -------------------------------------------------------------


def test_match_ignores_column_names_and_unordered_rows():
    assert results_match([("b", 2.0), ("a", 1.0)], [("a", 1.0), ("b", 2.0)], order_matters=False)


def test_match_respects_order_when_required():
    assert not results_match([("b", 2.0), ("a", 1.0)], [("a", 1.0), ("b", 2.0)], order_matters=True)


def test_match_tolerates_float_rounding_and_extra_columns():
    assert results_match([(10, "a", 100.004)], [("a", 100.0)], order_matters=True)


def test_match_rejects_different_values_or_row_counts():
    assert not results_match([("a", 120.0)], [("a", 100.0)], order_matters=True)
    assert not results_match([("a", 1.0)], [("a", 1.0), ("b", 2.0)], order_matters=False)


def test_match_normalises_month_formats():
    assert results_match([("2025-01", 5)], [("2025-01-01", 5)], order_matters=True)
    assert results_match([("2025-01-01T00:00:00", 5)], [("2025-01-01", 5)], order_matters=True)
    assert not results_match([("2025-02", 5)], [("2025-01-01", 5)], order_matters=True)


def test_match_tolerates_swapped_columns():
    assert results_match([(1.0, "a")], [("a", 1.0)], order_matters=True)


# --- eval data integrity ---------------------------------------------------------------


def test_golden_set_has_20_valid_reference_queries():
    from app.nodes.validate_sql import validate_sql

    golden = load_jsonl(EVAL_DIR / "golden.jsonl")
    assert len(golden) == 20
    assert len({g["qid"] for g in golden}) == 20
    for item in golden:
        assert validate_sql(item["reference_sql"]).ok, item["qid"]


def test_few_shot_examples_are_not_in_the_golden_set():
    from app.prompts import load_prompt

    prompt = load_prompt("write_sql", "v1")
    for item in load_jsonl(EVAL_DIR / "golden.jsonl"):
        assert item["question"] not in prompt


def _one_question_golden(tmp_path):
    path = tmp_path / "golden.jsonl"
    item = {"qid": "T1", "question": "Top categories by revenue", "reference_sql": GOOD_SQL, "order_matters": True}
    path.write_text(json.dumps(item) + "\n", encoding="utf-8")
    return path


def test_attack_set_is_fully_blocked_even_with_a_compromised_model(tmp_path):
    """The model obeys the attacker and writes PII SQL; code and validator must still block all 10."""
    hostile_sql = "SELECT u.email, u.latitude FROM `bigquery-public-data.thelook_ecommerce.users` u"
    warehouse = FakeWarehouse()
    agent, deps = make_agent(FakeLlm([plan(hostile_sql)]), warehouse)

    summary = run_evaluation(agent, deps, workers=1, golden_path=_one_question_golden(tmp_path))

    assert summary["attackBlockRate"] == 1.0, [a for a in summary["attacks"] if not a["pass"]]
    assert all(not a["executed"] for a in summary["attacks"])
    assert summary["executionAccuracy"] == 0.0
    assert warehouse.executed == []


def test_golden_question_passes_when_results_match(tmp_path):
    agent, deps = make_agent(FakeLlm([plan()]))

    summary = run_evaluation(agent, deps, workers=1, golden_path=_one_question_golden(tmp_path))

    assert summary["executionAccuracy"] == 1.0
    assert summary["groundingViolations"] == 0
    assert summary["meanLlmCalls"] == 2
    assert summary["p50Ms"] >= 0


# --- HTTP layer ------------------------------------------------------------------------


def client_for(**setting_overrides):
    _, deps = make_agent(FakeLlm([plan()]), **setting_overrides)
    return TestClient(create_app(deps))


def test_healthz_reports_schema_loaded():
    with client_for() as client:
        body = client.get("/healthz").json()
    assert body == {"ok": True, "schemaLoaded": True, "promptVersion": "v1"}


def test_ask_endpoint_returns_answer():
    with client_for() as client:
        res = client.post("/v1/ask", json={"question": "Top categories", "uid": "u1", "requestId": "req-12345678"})
    assert res.status_code == 200
    assert res.json()["status"] == "answered"


def test_ask_rejects_extra_fields_and_bad_types():
    with client_for() as client:
        extra = client.post("/v1/ask", json={"question": "Top", "uid": "u", "requestId": "req-12345678", "x": 1})
        nosql = client.post("/v1/ask", json={"question": {"$gt": ""}, "uid": "u", "requestId": "req-12345678"})
    assert extra.status_code == 422
    assert nosql.status_code == 422


def test_internal_key_is_enforced_when_configured():
    body = {"question": "Top categories", "uid": "u1", "requestId": "req-12345678"}
    with client_for(internal_key="s3cret-key-value") as client:
        assert client.post("/v1/ask", json=body).status_code == 403
        assert client.post("/v1/ask", json=body, headers={"X-Internal-Key": "wrong"}).status_code == 403
        assert client.post("/v1/ask", json=body, headers={"X-Internal-Key": "s3cret-key-value"}).status_code == 200


def test_docs_are_disabled_outside_development():
    with client_for() as client:
        assert client.get("/docs").status_code == 404
