"""Phase 67D — 10 tests for ProcessManager endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.process_manager import ProcessManager
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_pm():
    return TestClient(create_app())


@pytest.fixture()
def client_with_pm():
    pm = ProcessManager()
    app = create_app(process_manager=pm)
    return TestClient(app), pm


# ── POST /api/v1/processes ───────────────────────────────────────────────────

def test_post_create_returns_200(client_with_pm):
    client, _ = client_with_pm
    resp = client.post("/api/v1/processes", json={
        "name": "order", "state": "pending", "context": {"x": 1},
    })
    assert resp.status_code == 200


def test_post_response_has_required_keys(client_with_pm):
    client, _ = client_with_pm
    data = client.post("/api/v1/processes", json={
        "name": "order", "state": "pending",
    }).json()
    for k in ("process_id", "state", "context"):
        assert k in data
    assert data["state"] == "pending"


def test_post_no_manager_returns_error(client_no_pm):
    data = client_no_pm.post("/api/v1/processes", json={
        "name": "order", "state": "pending",
    }).json()
    assert "error" in data


def test_post_missing_name_400(client_with_pm):
    client, _ = client_with_pm
    resp = client.post("/api/v1/processes", json={"state": "pending"})
    assert resp.status_code == 400


def test_post_missing_state_400(client_with_pm):
    client, _ = client_with_pm
    resp = client.post("/api/v1/processes", json={"name": "order"})
    assert resp.status_code == 400


# ── POST /api/v1/processes/{id}/transition ───────────────────────────────────

def test_post_transition_returns_new_state(client_with_pm):
    client, _ = client_with_pm
    created = client.post("/api/v1/processes", json={
        "name": "order", "state": "pending",
    }).json()
    pid = created["process_id"]
    data = client.post(f"/api/v1/processes/{pid}/transition", json={
        "trigger": "approve", "state": "approved",
    }).json()
    assert data["state"] == "approved"
    assert len(data["history"]) == 1


def test_post_transition_missing_trigger_400(client_with_pm):
    client, _ = client_with_pm
    created = client.post("/api/v1/processes", json={
        "name": "order", "state": "pending",
    }).json()
    pid = created["process_id"]
    resp = client.post(f"/api/v1/processes/{pid}/transition", json={"state": "x"})
    assert resp.status_code == 400


# ── GET /api/v1/processes/{id} ───────────────────────────────────────────────

def test_get_by_id_returns_correct_process(client_with_pm):
    client, _ = client_with_pm
    created = client.post("/api/v1/processes", json={
        "name": "order", "state": "pending",
    }).json()
    pid = created["process_id"]
    data = client.get(f"/api/v1/processes/{pid}").json()
    assert data["process_id"] == pid


def test_get_unknown_id_404(client_with_pm):
    client, _ = client_with_pm
    resp = client.get("/api/v1/processes/phantom-id")
    assert resp.status_code == 404


# ── GET /api/v1/processes ────────────────────────────────────────────────────

def test_get_list_returns_processes_key(client_with_pm):
    client, _ = client_with_pm
    client.post("/api/v1/processes", json={"name": "order", "state": "pending"})
    data = client.get("/api/v1/processes").json()
    assert "processes" in data
    assert len(data["processes"]) >= 1
