"""Persistence: audit log, answer cache and eval runs.

Firestore in production (Google-managed, works on the Firebase Spark plan); an in-memory
store with the same interface for tests and local development.

Layout:
  users/{uid}/queries/{requestId}  one audit record per request (no result rows)
  cache/{sha256}                   cached response, expires after CACHE_TTL_SECONDS
  eval_runs/{auto}                 run_eval.py summaries
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import re
import threading
from typing import Protocol

_TRAILING_PUNCT = re.compile(r"[\s?.!;,]+$")


def normalize_question(question: str) -> str:
    return _TRAILING_PUNCT.sub("", " ".join(question.lower().split()))


def cache_key(question: str, model: str, prompt_version: str) -> str:
    """sha256(normalized question + model + prompt version)."""
    material = f"{normalize_question(question)}\n{model}\n{prompt_version}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


_TIMEOUT = 15  # seconds; tolerant of Firestore cold starts. All store calls are non-fatal (see main._safely).


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Store(Protocol):
    def get_cached(self, key: str) -> dict | None: ...

    def save_cached(self, key: str, response: dict, ttl_seconds: int) -> None: ...

    def save_query(self, record: dict) -> None: ...

    def list_history(self, uid: str, limit: int) -> list[dict]: ...

    def latest_eval(self) -> dict | None: ...

    def save_eval(self, summary: dict) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self.cache: dict[str, dict] = {}
        self.queries: list[dict] = []
        self.evals: list[dict] = []
        self._lock = threading.Lock()

    def get_cached(self, key: str) -> dict | None:
        entry = self.cache.get(key)
        if not entry or entry["expiresAt"] <= _now():
            return None
        return copy.deepcopy(entry["response"])

    def save_cached(self, key: str, response: dict, ttl_seconds: int) -> None:
        expires = _now() + dt.timedelta(seconds=ttl_seconds)
        self.cache[key] = {"response": copy.deepcopy(response), "expiresAt": expires}

    def save_query(self, record: dict) -> None:
        with self._lock:
            self.queries.append({**copy.deepcopy(record), "createdAt": _now()})

    def list_history(self, uid: str, limit: int) -> list[dict]:
        mine = [q for q in self.queries if q["uid"] == uid]
        return sorted(mine, key=lambda q: q["createdAt"], reverse=True)[:limit]

    def latest_eval(self) -> dict | None:
        return copy.deepcopy(self.evals[-1]) if self.evals else None

    def save_eval(self, summary: dict) -> None:
        self.evals.append(copy.deepcopy(summary))


class FirestoreStore:
    def __init__(self, project: str | None, credentials=None) -> None:
        from google.cloud import firestore

        self._firestore = firestore
        self._db = firestore.Client(project=project, credentials=credentials)

    def get_cached(self, key: str) -> dict | None:
        snapshot = self._db.collection("cache").document(key).get(timeout=_TIMEOUT)
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        return data["response"] if data.get("expiresAt") and data["expiresAt"] > _now() else None

    def save_cached(self, key: str, response: dict, ttl_seconds: int) -> None:
        # A Firestore TTL policy on `expiresAt` deletes stale entries (see README).
        expires = _now() + dt.timedelta(seconds=ttl_seconds)
        self._db.collection("cache").document(key).set({"response": response, "expiresAt": expires}, timeout=_TIMEOUT)

    def save_query(self, record: dict) -> None:
        ref = self._db.collection("users").document(record["uid"]).collection("queries")
        # Document id = requestId, so a retried write never creates a duplicate audit row.
        doc = {**record, "createdAt": self._firestore.SERVER_TIMESTAMP}
        ref.document(record["requestId"]).set(doc, timeout=_TIMEOUT)

    def list_history(self, uid: str, limit: int) -> list[dict]:
        query = (
            self._db.collection("users")
            .document(uid)
            .collection("queries")
            .order_by("createdAt", direction=self._firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [doc.to_dict() for doc in query.stream(timeout=_TIMEOUT)]

    def latest_eval(self) -> dict | None:
        query = self._db.collection("eval_runs").order_by(
            "startedAt", direction=self._firestore.Query.DESCENDING
        ).limit(1)
        docs = list(query.stream(timeout=_TIMEOUT))
        return docs[0].to_dict() if docs else None

    def save_eval(self, summary: dict) -> None:
        self._db.collection("eval_runs").add(summary, timeout=_TIMEOUT)
