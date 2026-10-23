"""Adapters for Gemini, BigQuery and Firestore, exercised with in-process fakes (no network)."""

import datetime as dt
import decimal
import json
from types import SimpleNamespace

import pytest
from google.api_core import exceptions as gexc

from app import llm as llm_module
from app.bq import BigQueryWarehouse, QueryError, to_json_value
from app.llm import GeminiLlm, LlmUnavailable
from app.schema_cache import SchemaCache, build_ddl
from app.store import FirestoreStore, MemoryStore, cache_key, normalize_question

# --- Gemini ------------------------------------------------------------------------------


class ApiFailure(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.models = []

    def generate_content(self, model, contents, config):
        self.models.append(model)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        usage = SimpleNamespace(prompt_token_count=11, candidates_token_count=7)
        return SimpleNamespace(text=outcome, usage_metadata=usage)


def gemini(outcomes, monkeypatch):
    from google.genai import types

    monkeypatch.setattr(llm_module.time, "sleep", lambda _s: None)
    client = object.__new__(GeminiLlm)
    client._types = types
    client._fallback_model = "lite"
    client._client = SimpleNamespace(models=FakeModels(outcomes))
    return client


def test_gemini_success_reports_tokens(monkeypatch):
    client = gemini(['{"ok": true}'], monkeypatch)
    result = client.generate("p", model="flash", json_schema={"type": "object"})
    assert (result.text, result.model, result.input_tokens, result.output_tokens) == ('{"ok": true}', "flash", 11, 7)


def test_gemini_retries_429_once_then_succeeds(monkeypatch):
    client = gemini([ApiFailure(429), "ok"], monkeypatch)
    assert client.generate("p", model="flash").text == "ok"
    assert client._client.models.models == ["flash", "flash"]


def test_gemini_falls_back_to_lite_after_retry(monkeypatch):
    client = gemini([ApiFailure(503), ApiFailure(500), "from lite"], monkeypatch)
    result = client.generate("p", model="flash")
    assert (result.text, result.model) == ("from lite", "lite")


def test_gemini_gives_up_with_llm_unavailable(monkeypatch):
    client = gemini([ApiFailure(429)] * 3, monkeypatch)
    with pytest.raises(LlmUnavailable):
        client.generate("p", model="flash")


def test_gemini_does_not_retry_client_errors(monkeypatch):
    client = gemini([ApiFailure(400)], monkeypatch)
    with pytest.raises(LlmUnavailable):
        client.generate("p", model="flash")
    assert client._client.models.models == ["flash"]


def test_gemini_timeouts_are_retryable(monkeypatch):
    client = gemini([TimeoutError(), "ok"], monkeypatch)
    assert client.generate("p", model="flash").text == "ok"


# --- BigQuery ----------------------------------------------------------------------------


class FakeJob:
    def __init__(self, rows=None, schema=None):
        self.total_bytes_processed = 4096
        self.job_id = "job_42"
        self.cache_hit = True
        self._rows, self._schema = rows or [], schema or []

    def result(self, timeout, max_results):
        return _Rows(self._rows, self._schema)


class _Rows(list):
    def __init__(self, rows, schema):
        super().__init__(rows)
        self.schema = schema


class FakeBqClient:
    def __init__(self, job=None, error=None):
        self.job, self.error, self.configs = job or FakeJob(), error, []

    def query(self, sql, job_config, timeout):
        self.configs.append(job_config)
        if self.error:
            raise self.error
        return self.job

    def get_table(self, table, timeout):
        field = SimpleNamespace(name="order_id", field_type="INTEGER", description="")
        return SimpleNamespace(schema=[field])


def warehouse(client):
    from google.cloud import bigquery

    wh = object.__new__(BigQueryWarehouse)
    wh._bq, wh._client, wh._max_bytes = bigquery, client, 1_000_000_000
    return wh


def test_dry_run_returns_estimate_without_cache():
    client = FakeBqClient()
    assert warehouse(client).dry_run("SELECT 1") == 4096
    config = client.configs[0]
    assert config.dry_run is True and config.use_query_cache is False


def test_execute_sets_cost_cap_cache_label_and_normalises_rows():
    schema = [
        SimpleNamespace(name="day", field_type="DATE"),
        SimpleNamespace(name="revenue", field_type="NUMERIC"),
        SimpleNamespace(name="n", field_type="INTEGER"),
    ]
    rows = [{"day": dt.date(2025, 1, 2), "revenue": decimal.Decimal("10.50"), "n": 3}]
    client = FakeBqClient(job=FakeJob(rows=[_Row(r) for r in rows], schema=schema))

    result = warehouse(client).execute("SELECT 1")

    config = client.configs[0]
    assert config.maximum_bytes_billed == 1_000_000_000
    assert config.use_query_cache is True
    assert config.labels == {"app": "insightpilot"}
    assert result.columns == [
        {"name": "day", "type": "DATE"},
        {"name": "revenue", "type": "NUMERIC"},
        {"name": "n", "type": "INT64"},
    ]
    assert result.rows == [{"day": "2025-01-02", "revenue": 10.5, "n": 3}]
    assert (result.job_id, result.bytes_processed, result.cache_hit) == ("job_42", 4096, True)


class _Row(dict):
    pass


@pytest.mark.parametrize("method", ["dry_run", "execute"])
def test_bigquery_errors_become_query_errors(method):
    client = FakeBqClient(error=gexc.BadRequest("Unrecognized name: revenu at [1:8]"))
    with pytest.raises(QueryError, match="Unrecognized name"):
        getattr(warehouse(client), method)("SELECT revenu")


def test_table_schema_normalises_types():
    assert warehouse(FakeBqClient()).table_schema("t") == [{"name": "order_id", "type": "INT64", "description": ""}]


def test_to_json_value_handles_bigquery_types():
    value = {"t": dt.datetime(2025, 1, 1, 12), "b": b"\x01", "l": [decimal.Decimal("1.5")]}
    assert to_json_value(value) == {"t": "2025-01-01T12:00:00", "b": "01", "l": [1.5]}


# --- Schema cache ------------------------------------------------------------------------


def test_build_ddl_hides_pii_and_geography():
    ddl = build_ddl(
        {
            "users": [
                {"name": "id", "type": "INT64"},
                {"name": "email", "type": "STRING"},
                {"name": "country", "type": "STRING"},
                {"name": "user_geom", "type": "GEOGRAPHY"},
            ]
        }
    )
    assert "country STRING" in ddl and "id INT64" in ddl
    assert "email" not in ddl and "user_geom" not in ddl
    assert "Join keys:" in ddl


def test_schema_cache_loads_every_allowlisted_table():
    cache = SchemaCache()
    assert not cache.loaded
    cache.load(warehouse(FakeBqClient()))
    assert cache.loaded
    assert cache.ddl.count("thelook_ecommerce.") == 7


# --- Store -------------------------------------------------------------------------------


def test_cache_key_normalisation():
    assert normalize_question("  Top 5   Categories?! ") == "top 5 categories"
    assert cache_key("Top 5 categories", "m", "v1") == cache_key("top 5   CATEGORIES?", "m", "v1")
    assert cache_key("q", "m1", "v1") != cache_key("q", "m2", "v1")


def test_memory_cache_expires():
    store = MemoryStore()
    store.save_cached("k", {"a": 1}, ttl_seconds=-1)
    assert store.get_cached("k") is None
    store.save_cached("k", {"a": 1}, ttl_seconds=60)
    assert store.get_cached("k") == {"a": 1}


class FakeDoc:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def get(self, timeout):
        data = self.db.data.get(self.path)
        return SimpleNamespace(exists=data is not None, to_dict=lambda: data)

    def set(self, data, timeout):
        self.db.data[self.path] = data

    def collection(self, name):
        return FakeCollection(self.db, f"{self.path}/{name}")


class FakeCollection:
    def __init__(self, db, path):
        self.db, self.path, self._limit = db, path, None

    def document(self, doc_id):
        return FakeDoc(self.db, f"{self.path}/{doc_id}")

    def add(self, data, timeout):
        self.db.data[f"{self.path}/{len(self.db.data)}"] = data

    def order_by(self, field, direction):
        self._order = field
        return self

    def limit(self, n):
        self._limit = n
        return self

    def stream(self, timeout):
        docs = [d for p, d in self.db.data.items() if p.rsplit("/", 1)[0] == self.path]
        docs.sort(key=lambda d: d[self._order], reverse=True)
        return [SimpleNamespace(to_dict=lambda d=d: d) for d in docs[: self._limit]]


class FakeFirestore:
    def __init__(self):
        self.data = {}

    def collection(self, name):
        return FakeCollection(self, name)


def firestore_store():
    store = object.__new__(FirestoreStore)
    store._db = FakeFirestore()
    store._firestore = SimpleNamespace(
        SERVER_TIMESTAMP=dt.datetime.now(dt.UTC), Query=SimpleNamespace(DESCENDING="desc")
    )
    return store


def test_firestore_cache_round_trip_and_expiry():
    store = firestore_store()
    assert store.get_cached("k") is None
    store.save_cached("k", {"answer": 1}, ttl_seconds=60)
    assert store.get_cached("k") == {"answer": 1}
    store.save_cached("k", {"answer": 1}, ttl_seconds=-1)
    assert store.get_cached("k") is None


def test_firestore_audit_is_per_user_and_idempotent():
    store = firestore_store()
    store.save_query({"uid": "alice", "requestId": "r1", "question": "q1"})
    store.save_query({"uid": "alice", "requestId": "r1", "question": "q1"})  # retried write
    store.save_query({"uid": "bob", "requestId": "r2", "question": "q2"})
    assert [q["question"] for q in store.list_history("alice", 20)] == ["q1"]


def test_firestore_latest_eval():
    store = firestore_store()
    assert store.latest_eval() is None
    store.save_eval({"startedAt": "2026-10-01", "executionAccuracy": 0.8})
    store.save_eval({"startedAt": "2026-10-23", "executionAccuracy": 0.9})
    assert store.latest_eval()["executionAccuracy"] == 0.9


# --- Service-account parsing -------------------------------------------------------------


def test_service_account_json_parsing(monkeypatch):
    from app.main import _service_account_info

    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    assert _service_account_info() is None
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{not json")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        _service_account_info()
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps({"type": "authorized_user"}))
    with pytest.raises(RuntimeError, match="service account"):
        _service_account_info()
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps({"type": "service_account", "project_id": "p"}))
    assert _service_account_info()["project_id"] == "p"


# --- write_sql output parsing ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "not valid JSON"),
        ("[1, 2]", "answerable"),
        ('{"answerable": "yes", "sql": "SELECT 1"}', "answerable"),
        ('{"answerable": true, "sql": 5}', "must be a string"),
        ('{"answerable": true, "sql": "  "}', "returned no SQL"),
    ],
)
def test_parse_plan_rejects_malformed_output(text, message):
    from app.nodes.write_sql import parse_plan

    with pytest.raises(ValueError, match=message):
        parse_plan(text)


def test_parse_plan_accepts_fenced_json_and_caps_assumptions():
    from app.nodes.write_sql import parse_plan

    fenced = '```json\n{"answerable": true, "sql": "SELECT 1", "assumptions": ["a", "b", "c", "d"]}\n```'
    plan = parse_plan(fenced)
    assert plan.sql == "SELECT 1"
    assert plan.assumptions == ["a", "b", "c"]
