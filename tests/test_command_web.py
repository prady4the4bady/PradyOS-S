"""Phase 64D — 10 tests for CommandBus endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.command_bus import CommandBus
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_bus():
    return TestClient(create_app())


@pytest.fixture()
def client_with_bus():
    bus = CommandBus()
    bus.register("echo", lambda p: {"echo": p})
    app = create_app(command_bus=bus)
    return TestClient(app), bus


# ── GET /api/v1/commands/handlers ────────────────────────────────────────────

def test_get_handlers_returns_200_with_key(client_with_bus):
    client, _ = client_with_bus
    data = client.get("/api/v1/commands/handlers").json()
    assert "handlers" in data
    assert "echo" in data["handlers"]


def test_get_handlers_no_bus_empty(client_no_bus):
    data = client_no_bus.get("/api/v1/commands/handlers").json()
    assert data["handlers"] == []


# ── POST /api/v1/commands/dispatch ───────────────────────────────────────────

def test_post_dispatch_returns_success_true(client_with_bus):
    client, _ = client_with_bus
    data = client.post("/api/v1/commands/dispatch",
                       json={"name": "echo", "payload": {"x": 1}}).json()
    assert data["success"] is True
    assert data["result"] == {"echo": {"x": 1}}


def test_post_dispatch_response_has_required_fields(client_with_bus):
    client, _ = client_with_bus
    data = client.post("/api/v1/commands/dispatch",
                       json={"name": "echo", "payload": {}}).json()
    for k in ("command_name", "result", "duration_ms"):
        assert k in data


def test_post_dispatch_no_bus_returns_error(client_no_bus):
    data = client_no_bus.post("/api/v1/commands/dispatch",
                               json={"name": "echo"}).json()
    assert "error" in data


def test_post_dispatch_missing_name_400(client_with_bus):
    client, _ = client_with_bus
    resp = client.post("/api/v1/commands/dispatch", json={"payload": {}})
    assert resp.status_code == 400


# ── GET /api/v1/commands/history ─────────────────────────────────────────────

def test_get_history_returns_200_with_key(client_with_bus):
    client, _ = client_with_bus
    client.post("/api/v1/commands/dispatch",
                json={"name": "echo", "payload": {}})
    data = client.get("/api/v1/commands/history").json()
    assert "history" in data
    assert len(data["history"]) >= 1


def test_get_history_no_bus_empty(client_no_bus):
    data = client_no_bus.get("/api/v1/commands/history").json()
    assert data["history"] == []


# ── DELETE /api/v1/commands/handlers/{name} ──────────────────────────────────

def test_delete_handler_returns_unregistered_true(client_with_bus):
    client, _ = client_with_bus
    resp = client.delete("/api/v1/commands/handlers/echo")
    assert resp.status_code == 200
    assert resp.json()["unregistered"] is True


def test_delete_unknown_handler_404(client_with_bus):
    client, _ = client_with_bus
    resp = client.delete("/api/v1/commands/handlers/phantom")
    assert resp.status_code == 404
