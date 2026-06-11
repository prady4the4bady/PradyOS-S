"""Phase 36D — 10 tests for OS state endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.state_manager import StateManager
from pradyos.core.snapshot_store import SnapshotStore
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_sm():
    return TestClient(create_app())


@pytest.fixture()
def client_with_sm():
    sm = StateManager(snapshot_store=SnapshotStore())
    app = create_app(state_manager=sm)
    return TestClient(app), sm


# ── GET /api/v1/os/status ─────────────────────────────────────────────────────

def test_get_os_status_returns_200(client_no_sm):
    assert client_no_sm.get("/api/v1/os/status").status_code == 200


def test_get_os_status_no_sm_store_disconnected(client_no_sm):
    data = client_no_sm.get("/api/v1/os/status").json()
    assert data["store_connected"] is False


# ── POST /api/v1/os/shutdown ──────────────────────────────────────────────────

def test_post_shutdown_returns_200(client_no_sm):
    assert client_no_sm.post("/api/v1/os/shutdown", json={}).status_code == 200


def test_post_shutdown_no_sm_empty_results_with_message(client_no_sm):
    data = client_no_sm.post("/api/v1/os/shutdown", json={}).json()
    assert data["results"] == []
    assert "message" in data


def test_post_shutdown_fires_hooks(client_with_sm):
    client, sm = client_with_sm
    sm.register_hook("disk_flush", lambda: None)
    data = client.post("/api/v1/os/shutdown", json={}).json()
    assert "disk_flush:ok" in data["results"]


# ── GET /api/v1/os/state/{module} ─────────────────────────────────────────────

def test_get_state_module_returns_200(client_with_sm):
    client, _ = client_with_sm
    assert client.get("/api/v1/os/state/intent").status_code == 200


def test_get_state_module_no_sm_empty_keys(client_no_sm):
    data = client_no_sm.get("/api/v1/os/state/intent").json()
    assert data["keys"] == []


# ── POST /api/v1/os/state/{module}/{key} ──────────────────────────────────────

def test_post_state_no_sm_returns_error(client_no_sm):
    data = client_no_sm.post("/api/v1/os/state/intent/cfg",
                              json={"data": {"x": 1}}).json()
    assert "error" in data


# ── GET /api/v1/os/state/{module}/{key} unknown → 404 ────────────────────────

def test_get_state_unknown_returns_404(client_with_sm):
    client, _ = client_with_sm
    resp = client.get("/api/v1/os/state/intent/phantom")
    assert resp.status_code == 404


# ── full flow ─────────────────────────────────────────────────────────────────

def test_full_flow_save_then_load_returns_data(client_with_sm):
    client, _ = client_with_sm
    client.post("/api/v1/os/state/intent/cfg", json={"data": {"strategy": "patient"}})
    loaded = client.get("/api/v1/os/state/intent/cfg").json()
    assert loaded["data"] == {"strategy": "patient"}
    assert loaded["version"] == 1
