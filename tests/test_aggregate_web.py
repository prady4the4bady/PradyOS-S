"""Phase 63D — 10 tests for AggregateRegistry endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.aggregate_root import AggregateRegistry
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_reg():
    return TestClient(create_app())


@pytest.fixture()
def client_with_reg():
    reg = AggregateRegistry()
    app = create_app(aggregate_registry=reg)
    return TestClient(app), reg


# ── GET /api/v1/aggregates ───────────────────────────────────────────────────

def test_get_aggregates_returns_200_with_key(client_with_reg):
    client, _ = client_with_reg
    data = client.get("/api/v1/aggregates").json()
    assert "aggregates" in data


def test_get_no_registry_empty(client_no_reg):
    data = client_no_reg.get("/api/v1/aggregates").json()
    assert data["aggregates"] == []


# ── POST .../events ──────────────────────────────────────────────────────────

def test_post_events_returns_200(client_with_reg):
    client, _ = client_with_reg
    resp = client.post("/api/v1/aggregates/u1/events",
                       json={"event_type": "created", "payload": {"name": "alice"}})
    assert resp.status_code == 200


def test_post_events_response_has_version_1(client_with_reg):
    client, _ = client_with_reg
    data = client.post("/api/v1/aggregates/u1/events",
                       json={"event_type": "created", "payload": {}}).json()
    assert data["version"] == 1
    assert data["aggregate_id"] == "u1"
    assert data["event_type"] == "created"


def test_post_events_no_registry_returns_error(client_no_reg):
    data = client_no_reg.post("/api/v1/aggregates/u1/events",
                               json={"event_type": "x"}).json()
    assert "error" in data


# ── GET .../state ────────────────────────────────────────────────────────────

def test_get_state_returns_dict(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/aggregates/u1/events",
                json={"event_type": "created", "payload": {"name": "bob"}})
    data = client.get("/api/v1/aggregates/u1/state").json()
    assert data["aggregate_id"] == "u1"
    assert data["state"] == {"name": "bob"}


def test_get_state_unknown_returns_404(client_with_reg):
    client, _ = client_with_reg
    resp = client.get("/api/v1/aggregates/unknown/state")
    assert resp.status_code == 404


# ── GET .../events ───────────────────────────────────────────────────────────

def test_get_events_returns_list(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/aggregates/u1/events", json={"event_type": "a"})
    client.post("/api/v1/aggregates/u1/events", json={"event_type": "b"})
    data = client.get("/api/v1/aggregates/u1/events").json()
    assert len(data["events"]) == 2


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_returns_deleted_true(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/aggregates/u1/events", json={"event_type": "x"})
    resp = client.delete("/api/v1/aggregates/u1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


# ── since_version query ──────────────────────────────────────────────────────

def test_since_version_skips_earlier_events(client_with_reg):
    client, _ = client_with_reg
    client.post("/api/v1/aggregates/u1/events",
                json={"event_type": "a", "payload": {"a": 1}})
    e2 = client.post("/api/v1/aggregates/u1/events",
                     json={"event_type": "b", "payload": {"b": 2}}).json()
    assert e2["version"] == 2
    data = client.get("/api/v1/aggregates/u1/events?since_version=1").json()
    assert len(data["events"]) == 1
    assert data["events"][0]["version"] == 2
