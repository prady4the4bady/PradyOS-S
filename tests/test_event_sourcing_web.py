"""Phase 48D — 10 tests for EventStore endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.event_store import EventStore
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_store():
    return TestClient(create_app())


@pytest.fixture()
def client_with_store():
    es = EventStore()
    app = create_app(event_store=es)
    return TestClient(app), es


# ── POST append ───────────────────────────────────────────────────────────────

def test_post_append_returns_event_fields(client_with_store):
    client, _ = client_with_store
    data = client.post("/api/v1/events/orders",
                       json={"event_type": "created", "payload": {"id": 1}}).json()
    for key in ("id", "stream", "event_type", "payload", "sequence", "occurred_at"):
        assert key in data
    assert data["sequence"] == 1
    assert data["event_type"] == "created"


def test_post_missing_event_type_400(client_with_store):
    client, _ = client_with_store
    resp = client.post("/api/v1/events/orders", json={"payload": {}})
    assert resp.status_code == 400


def test_post_no_event_store_400(client_no_store):
    resp = client_no_store.post("/api/v1/events/orders",
                                 json={"event_type": "x", "payload": {}})
    assert resp.status_code == 400


# ── GET read ──────────────────────────────────────────────────────────────────

def test_get_returns_events_and_count(client_with_store):
    client, _ = client_with_store
    client.post("/api/v1/events/s", json={"event_type": "x"})
    data = client.get("/api/v1/events/s").json()
    assert "events" in data
    assert "count" in data
    assert data["count"] == 1


def test_get_from_seq_zero_returns_all(client_with_store):
    client, _ = client_with_store
    for i in range(3):
        client.post("/api/v1/events/s", json={"event_type": f"e{i}"})
    data = client.get("/api/v1/events/s?from_seq=0").json()
    assert data["count"] == 3


def test_get_no_store_returns_empty_200(client_no_store):
    resp = client_no_store.get("/api/v1/events/anything")
    assert resp.status_code == 200
    assert resp.json()["events"] == []


# ── POST project ──────────────────────────────────────────────────────────────

def test_post_project_returns_state_key(client_with_store):
    client, _ = client_with_store
    resp = client.post("/api/v1/events/s/project",
                       json={"initial": {}, "reducer_steps": []})
    assert resp.status_code == 200
    assert "state" in resp.json()


def test_post_project_missing_reducer_steps_400(client_with_store):
    client, _ = client_with_store
    resp = client.post("/api/v1/events/s/project", json={"initial": {}})
    assert resp.status_code == 400


# ── full flow ─────────────────────────────────────────────────────────────────

def test_full_flow_append_two_then_project(client_with_store):
    client, _ = client_with_store
    client.post("/api/v1/events/orders",
                json={"event_type": "created", "payload": {"id": 1}})
    client.post("/api/v1/events/orders",
                json={"event_type": "paid", "payload": {"amount": 100}})
    data = client.post("/api/v1/events/orders/project", json={
        "initial": {"status": "none", "amount": 0},
        "reducer_steps": [
            {"match_type": "created", "updates": {"status": "open"}},
            {"match_type": "paid", "updates": {"status": "paid", "amount": 100}},
        ],
    }).json()
    assert data["state"]["status"] == "paid"
    assert data["state"]["amount"] == 100


def test_project_match_type_merges_updates(client_with_store):
    client, _ = client_with_store
    client.post("/api/v1/events/s", json={"event_type": "x"})
    data = client.post("/api/v1/events/s/project", json={
        "initial": {"hits": 0},
        "reducer_steps": [{"match_type": "x", "updates": {"hits": 1}}],
    }).json()
    assert data["state"]["hits"] == 1
