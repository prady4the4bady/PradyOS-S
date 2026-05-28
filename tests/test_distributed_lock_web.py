"""Phase 52D — 10 tests for LockManager endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.distributed_lock import LockManager
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_lm():
    return TestClient(create_app())


@pytest.fixture()
def client_with_lm():
    m = LockManager()
    app = create_app(lock_manager=m)
    return TestClient(app), m


# ── GET /api/v1/locks ─────────────────────────────────────────────────────────

def test_get_locks_returns_200(client_no_lm):
    assert client_no_lm.get("/api/v1/locks").status_code == 200


def test_get_locks_no_manager_empty(client_no_lm):
    data = client_no_lm.get("/api/v1/locks").json()
    assert data["locks"] == []
    assert data["count"] == 0


# ── POST /api/v1/locks ────────────────────────────────────────────────────────

def test_post_lock_missing_keys_400(client_with_lm):
    client, _ = client_with_lm
    resp = client.post("/api/v1/locks", json={"name": "x"})
    assert resp.status_code == 400


def test_post_lock_valid_returns_fields(client_with_lm):
    client, _ = client_with_lm
    data = client.post("/api/v1/locks",
                       json={"name": "res", "holder_id": "h1", "ttl": 60}).json()
    assert data["name"] == "res"
    assert data["holder_id"] == "h1"
    assert "expires_at" in data


def test_post_lock_already_held_409(client_with_lm):
    client, _ = client_with_lm
    client.post("/api/v1/locks", json={"name": "res", "holder_id": "h1"})
    resp = client.post("/api/v1/locks", json={"name": "res", "holder_id": "h2"})
    assert resp.status_code == 409


def test_post_no_manager_400(client_no_lm):
    resp = client_no_lm.post("/api/v1/locks",
                              json={"name": "x", "holder_id": "y"})
    assert resp.status_code == 400


# ── DELETE /api/v1/locks/{name} ───────────────────────────────────────────────

def test_delete_lock_returns_released_true(client_with_lm):
    client, _ = client_with_lm
    client.post("/api/v1/locks", json={"name": "res", "holder_id": "h1"})
    resp = client.delete("/api/v1/locks/res?holder_id=h1")
    assert resp.status_code == 200
    assert resp.json()["released"] is True


def test_delete_unknown_lock_404(client_with_lm):
    client, _ = client_with_lm
    resp = client.delete("/api/v1/locks/phantom?holder_id=h1")
    assert resp.status_code == 404


# ── POST /api/v1/locks/{name}/refresh ─────────────────────────────────────────

def test_post_refresh_returns_refreshed_true(client_with_lm):
    client, _ = client_with_lm
    client.post("/api/v1/locks", json={"name": "res", "holder_id": "h1"})
    resp = client.post("/api/v1/locks/res/refresh",
                       json={"holder_id": "h1", "ttl": 120})
    assert resp.status_code == 200
    assert resp.json()["refreshed"] is True


def test_post_refresh_wrong_holder_404(client_with_lm):
    client, _ = client_with_lm
    client.post("/api/v1/locks", json={"name": "res", "holder_id": "h1"})
    resp = client.post("/api/v1/locks/res/refresh",
                       json={"holder_id": "h2"})
    assert resp.status_code == 404
