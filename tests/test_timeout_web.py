"""Phase 56D — 10 tests for TimeoutGuard endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.timeout_guard import TimeoutGuard
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_guard():
    return TestClient(create_app())


@pytest.fixture()
def client_with_guard():
    g = TimeoutGuard(default_timeout=1.0)
    app = create_app(timeout_guard=g)
    return TestClient(app), g


# ── GET /api/v1/timeouts ─────────────────────────────────────────────────────

def test_get_timeouts_returns_200(client_no_guard):
    assert client_no_guard.get("/api/v1/timeouts").status_code == 200


def test_get_timeouts_has_required_keys(client_with_guard):
    client, _ = client_with_guard
    data = client.get("/api/v1/timeouts").json()
    assert "names" in data
    assert "total" in data


def test_get_no_guard_total_zero(client_no_guard):
    data = client_no_guard.get("/api/v1/timeouts").json()
    assert data["total"] == 0


# ── POST /api/v1/timeouts/execute ────────────────────────────────────────────

def test_post_execute_success_returns_200(client_with_guard):
    client, _ = client_with_guard
    resp = client.post("/api/v1/timeouts/execute", json={"name": "svc"})
    assert resp.status_code == 200


def test_post_execute_response_outcome_success(client_with_guard):
    client, _ = client_with_guard
    data = client.post("/api/v1/timeouts/execute", json={"name": "svc"}).json()
    assert data["outcome"] == "success"


def test_post_execute_timeout_returns_408(client_with_guard):
    client, _ = client_with_guard
    resp = client.post("/api/v1/timeouts/execute", json={
        "name": "svc", "sleep": 1.0, "timeout": 0.05,
    })
    assert resp.status_code == 408


def test_post_execute_timeout_outcome(client_with_guard):
    client, _ = client_with_guard
    data = client.post("/api/v1/timeouts/execute", json={
        "name": "svc", "sleep": 1.0, "timeout": 0.05,
    }).json()
    assert data["outcome"] == "timeout"


def test_post_execute_should_error_returns_500(client_with_guard):
    client, _ = client_with_guard
    resp = client.post("/api/v1/timeouts/execute", json={
        "name": "svc", "should_error": True,
    })
    assert resp.status_code == 500


# ── GET / DELETE history ─────────────────────────────────────────────────────

def test_get_history_returns_records(client_with_guard):
    client, _ = client_with_guard
    client.post("/api/v1/timeouts/execute", json={"name": "svc"})
    data = client.get("/api/v1/timeouts/svc/history").json()
    assert "records" in data
    assert len(data["records"]) == 1


def test_delete_history_returns_cleared_true(client_with_guard):
    client, _ = client_with_guard
    client.post("/api/v1/timeouts/execute", json={"name": "svc"})
    resp = client.delete("/api/v1/timeouts/svc/history")
    assert resp.status_code == 200
    assert resp.json()["cleared"] is True
