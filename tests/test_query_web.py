"""Phase 65D — 10 tests for QueryBus endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.query_bus import QueryBus
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_bus():
    return TestClient(create_app())


@pytest.fixture()
def client_with_bus():
    bus = QueryBus()
    bus.register("lookup", lambda params: {"found": params.get("id")})
    app = create_app(query_bus=bus)
    return TestClient(app), bus


# ── GET /api/v1/queries/handlers ─────────────────────────────────────────────

def test_get_handlers_returns_200_with_key(client_with_bus):
    client, _ = client_with_bus
    data = client.get("/api/v1/queries/handlers").json()
    assert "handlers" in data
    assert "lookup" in data["handlers"]


def test_get_handlers_no_bus_empty(client_no_bus):
    data = client_no_bus.get("/api/v1/queries/handlers").json()
    assert data["handlers"] == []


# ── POST /api/v1/queries/execute ─────────────────────────────────────────────

def test_post_execute_returns_success_true(client_with_bus):
    client, _ = client_with_bus
    data = client.post("/api/v1/queries/execute",
                       json={"name": "lookup", "params": {"id": "abc"}}).json()
    assert data["success"] is True
    assert data["result"] == {"found": "abc"}


def test_post_execute_response_has_required_fields(client_with_bus):
    client, _ = client_with_bus
    data = client.post("/api/v1/queries/execute",
                       json={"name": "lookup", "params": {}}).json()
    for k in ("query_name", "result", "duration_ms"):
        assert k in data


def test_post_execute_no_bus_returns_error(client_no_bus):
    data = client_no_bus.post("/api/v1/queries/execute",
                               json={"name": "lookup"}).json()
    assert "error" in data


def test_post_execute_missing_name_400(client_with_bus):
    client, _ = client_with_bus
    resp = client.post("/api/v1/queries/execute", json={"params": {}})
    assert resp.status_code == 400


# ── GET /api/v1/queries/history ──────────────────────────────────────────────

def test_get_history_returns_list_after_execute(client_with_bus):
    client, _ = client_with_bus
    client.post("/api/v1/queries/execute",
                json={"name": "lookup", "params": {"id": "x"}})
    data = client.get("/api/v1/queries/history").json()
    assert "history" in data
    assert len(data["history"]) >= 1


def test_get_history_no_bus_empty(client_no_bus):
    data = client_no_bus.get("/api/v1/queries/history").json()
    assert data["history"] == []


# ── DELETE /api/v1/queries/handlers/{name} ───────────────────────────────────

def test_delete_handler_returns_unregistered_true(client_with_bus):
    client, _ = client_with_bus
    resp = client.delete("/api/v1/queries/handlers/lookup")
    assert resp.status_code == 200
    assert resp.json()["unregistered"] is True


def test_delete_unknown_handler_404(client_with_bus):
    client, _ = client_with_bus
    resp = client.delete("/api/v1/queries/handlers/phantom")
    assert resp.status_code == 404
