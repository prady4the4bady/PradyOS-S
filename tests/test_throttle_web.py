"""Phase 59D — 10 tests for ThrottleMap endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.throttle_map import ThrottleMap
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_tm():
    return TestClient(create_app())


@pytest.fixture()
def client_with_tm():
    tm = ThrottleMap()
    app = create_app(throttle_map=tm)
    return TestClient(app), tm


# ── GET /api/v1/throttle ──────────────────────────────────────────────────────

def test_get_throttle_returns_200_with_keys_count(client_with_tm):
    client, _ = client_with_tm
    data = client.get("/api/v1/throttle").json()
    assert "keys" in data
    assert "count" in data


def test_get_no_throttle_empty(client_no_tm):
    data = client_no_tm.get("/api/v1/throttle").json()
    assert data["keys"] == []
    assert data["count"] == 0


# ── POST /api/v1/throttle/check ──────────────────────────────────────────────

def test_post_check_valid_returns_key_allowed(client_with_tm):
    client, _ = client_with_tm
    data = client.post("/api/v1/throttle/check", json={
        "key": "user:1", "limit": 5, "window": 60,
    }).json()
    assert data["key"] == "user:1"
    assert "allowed" in data


def test_post_check_first_call_allowed_true(client_with_tm):
    client, _ = client_with_tm
    data = client.post("/api/v1/throttle/check", json={
        "key": "fresh", "limit": 3, "window": 60,
    }).json()
    assert data["allowed"] is True


def test_post_check_missing_fields_returns_400(client_with_tm):
    client, _ = client_with_tm
    resp = client.post("/api/v1/throttle/check", json={"key": "x"})
    assert resp.status_code == 400


def test_post_check_no_throttle_returns_error(client_no_tm):
    data = client_no_tm.post("/api/v1/throttle/check", json={
        "key": "x", "limit": 1, "window": 1,
    }).json()
    assert "error" in data


# ── GET /api/v1/throttle/{key} ───────────────────────────────────────────────

def test_get_stats_after_check_returns_calls_in_window(client_with_tm):
    client, _ = client_with_tm
    client.post("/api/v1/throttle/check", json={
        "key": "u", "limit": 5, "window": 60,
    })
    client.post("/api/v1/throttle/check", json={
        "key": "u", "limit": 5, "window": 60,
    })
    resp = client.get("/api/v1/throttle/u?limit=5&window=60")
    assert resp.status_code == 200
    data = resp.json()
    assert data["calls_in_window"] == 2


def test_get_unknown_key_returns_404(client_with_tm):
    client, _ = client_with_tm
    resp = client.get("/api/v1/throttle/phantom?limit=5&window=60")
    assert resp.status_code == 404


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_returns_deleted_true(client_with_tm):
    client, _ = client_with_tm
    client.post("/api/v1/throttle/check", json={
        "key": "k", "limit": 1, "window": 60,
    })
    resp = client.delete("/api/v1/throttle/k")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_second_delete_returns_404(client_with_tm):
    client, _ = client_with_tm
    client.post("/api/v1/throttle/check", json={
        "key": "k", "limit": 1, "window": 60,
    })
    client.delete("/api/v1/throttle/k")
    resp = client.delete("/api/v1/throttle/k")
    assert resp.status_code == 404
