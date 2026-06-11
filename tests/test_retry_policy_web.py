"""Phase 54D — 10 tests for RetryPolicy endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.retry_policy import RetryPolicy
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_rp():
    return TestClient(create_app())


@pytest.fixture()
def client_with_rp():
    # base_delay=0 + jitter=0 makes web tests instantaneous
    p = RetryPolicy(max_attempts=3, base_delay=0.0, backoff_factor=2.0, jitter=0.0)
    app = create_app(retry_policy=p)
    return TestClient(app), p


# ── GET /api/v1/retry ─────────────────────────────────────────────────────────

def test_get_retry_returns_200(client_no_rp):
    assert client_no_rp.get("/api/v1/retry").status_code == 200


def test_get_retry_no_policy_empty(client_no_rp):
    data = client_no_rp.get("/api/v1/retry").json()
    assert data["names"] == []
    assert data["count"] == 0


# ── POST /api/v1/retry/execute ────────────────────────────────────────────────

def test_post_execute_success_returns_ok(client_with_rp):
    client, _ = client_with_rp
    data = client.post("/api/v1/retry/execute", json={"name": "svc"}).json()
    assert data["result"] == "ok"


def test_post_execute_response_has_required_keys(client_with_rp):
    client, _ = client_with_rp
    data = client.post("/api/v1/retry/execute", json={"name": "svc"}).json()
    for k in ("name", "result", "attempts", "error"):
        assert k in data


def test_post_execute_should_fail_once_succeeds_on_second(client_with_rp):
    client, _ = client_with_rp
    data = client.post("/api/v1/retry/execute", json={
        "name": "svc", "should_fail": True, "fail_attempts": 1,
    }).json()
    assert data["result"] == "ok"
    assert data["attempts"] == 2  # one failure + one success


def test_post_execute_should_fail_all_attempts_returns_error(client_with_rp):
    client, _ = client_with_rp
    data = client.post("/api/v1/retry/execute", json={
        "name": "svc", "should_fail": True, "fail_attempts": 3,
    }).json()
    assert data["result"] is None
    assert data["error"] is not None
    assert data["attempts"] == 3


def test_post_execute_no_policy_error(client_no_rp):
    data = client_no_rp.post("/api/v1/retry/execute", json={"name": "x"}).json()
    assert "error" in data


# ── GET /api/v1/retry/{name}/history ──────────────────────────────────────────

def test_get_history_after_execute(client_with_rp):
    client, _ = client_with_rp
    client.post("/api/v1/retry/execute", json={"name": "svc"})
    data = client.get("/api/v1/retry/svc/history").json()
    assert data["name"] == "svc"
    assert len(data["history"]) == 1


# ── DELETE /api/v1/retry/{name}/history ───────────────────────────────────────

def test_delete_history_returns_cleared_true(client_with_rp):
    client, _ = client_with_rp
    client.post("/api/v1/retry/execute", json={"name": "svc"})
    resp = client.delete("/api/v1/retry/svc/history")
    assert resp.status_code == 200
    assert resp.json()["cleared"] is True


def test_delete_history_unknown_404(client_with_rp):
    client, _ = client_with_rp
    resp = client.delete("/api/v1/retry/phantom/history")
    assert resp.status_code == 404
