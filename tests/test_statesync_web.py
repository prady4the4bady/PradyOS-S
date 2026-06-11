"""Phase 51D — 10 tests for StateSync endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.pubsub import PubSubBroker
from pradyos.core.statesync import StateSyncManager
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_ss():
    return TestClient(create_app())


@pytest.fixture()
def client_with_ss():
    mgr = StateSyncManager()
    a = PubSubBroker()
    b = PubSubBroker()
    mgr.register_broker("a", a)
    mgr.register_broker("b", b)
    app = create_app(statesync=mgr)
    return TestClient(app), mgr


def _payload(broker_a="a", broker_b="b", topics_a=None, topics_b=None) -> dict:
    return {
        "broker_a": broker_a,
        "broker_b": broker_b,
        "topics_a": topics_a if topics_a is not None else ["x"],
        "topics_b": topics_b if topics_b is not None else ["x"],
    }


# ── GET sessions ──────────────────────────────────────────────────────────────

def test_get_sessions_returns_200(client_no_ss):
    assert client_no_ss.get("/api/v1/statesync/sessions").status_code == 200


def test_get_sessions_no_ss_empty(client_no_ss):
    data = client_no_ss.get("/api/v1/statesync/sessions").json()
    assert data["sessions"] == []
    assert data["count"] == 0


# ── POST validation ──────────────────────────────────────────────────────────

def test_post_no_ss_400(client_no_ss):
    resp = client_no_ss.post("/api/v1/statesync/sessions", json=_payload())
    assert resp.status_code == 400


def test_post_missing_keys_400(client_with_ss):
    client, _ = client_with_ss
    resp = client.post("/api/v1/statesync/sessions",
                       json={"broker_a": "a", "broker_b": "b"})
    assert resp.status_code == 400


def test_post_unknown_broker_400(client_with_ss):
    client, _ = client_with_ss
    resp = client.post("/api/v1/statesync/sessions",
                       json=_payload(broker_a="missing"))
    assert resp.status_code == 400


# ── POST success + GET reflects ──────────────────────────────────────────────

def test_post_valid_returns_session_with_id_and_active(client_with_ss):
    client, _ = client_with_ss
    data = client.post("/api/v1/statesync/sessions", json=_payload()).json()
    assert "id" in data
    assert data["active"] is True


def test_get_sessions_count_one_after_post(client_with_ss):
    client, _ = client_with_ss
    client.post("/api/v1/statesync/sessions", json=_payload())
    data = client.get("/api/v1/statesync/sessions").json()
    assert data["count"] == 1


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_session_returns_stopped_true(client_with_ss):
    client, _ = client_with_ss
    sub = client.post("/api/v1/statesync/sessions", json=_payload()).json()
    resp = client.delete(f"/api/v1/statesync/sessions/{sub['id']}")
    assert resp.status_code == 200
    assert resp.json()["stopped"] is True


def test_delete_unknown_returns_404(client_with_ss):
    client, _ = client_with_ss
    resp = client.delete("/api/v1/statesync/sessions/phantom")
    assert resp.status_code == 404


# ── active_only after DELETE ─────────────────────────────────────────────────

def test_active_only_filter_after_delete(client_with_ss):
    client, _ = client_with_ss
    sub = client.post("/api/v1/statesync/sessions", json=_payload()).json()
    client.delete(f"/api/v1/statesync/sessions/{sub['id']}")
    data = client.get("/api/v1/statesync/sessions?active_only=true").json()
    assert data["count"] == 0
