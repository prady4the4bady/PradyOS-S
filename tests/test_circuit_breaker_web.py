"""Phase 53D — 10 tests for CircuitBreaker endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.circuit_breaker import CircuitBreaker
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_cb():
    return TestClient(create_app())


@pytest.fixture()
def client_with_cb():
    cb = CircuitBreaker()
    app = create_app(circuit_breaker=cb)
    return TestClient(app), cb


# ── GET /api/v1/breakers ──────────────────────────────────────────────────────

def test_get_breakers_returns_200(client_no_cb):
    assert client_no_cb.get("/api/v1/breakers").status_code == 200


def test_get_breakers_no_cb_empty(client_no_cb):
    data = client_no_cb.get("/api/v1/breakers").json()
    assert data["breakers"] == []
    assert data["count"] == 0


# ── POST /api/v1/breakers ─────────────────────────────────────────────────────

def test_post_missing_name_400(client_with_cb):
    client, _ = client_with_cb
    resp = client.post("/api/v1/breakers", json={})
    assert resp.status_code == 400


def test_post_valid_returns_closed_state(client_with_cb):
    client, _ = client_with_cb
    data = client.post("/api/v1/breakers", json={"name": "svc"}).json()
    assert data["name"] == "svc"
    assert data["state"] == "CLOSED"


def test_post_no_cb_400(client_no_cb):
    resp = client_no_cb.post("/api/v1/breakers", json={"name": "x"})
    assert resp.status_code == 400
    assert "error" in resp.json()


# ── GET /api/v1/breakers/{name} ───────────────────────────────────────────────

def test_get_breaker_by_name_after_register(client_with_cb):
    client, _ = client_with_cb
    client.post("/api/v1/breakers", json={"name": "svc"})
    resp = client.get("/api/v1/breakers/svc")
    assert resp.status_code == 200
    assert resp.json()["name"] == "svc"


def test_get_unknown_breaker_404(client_with_cb):
    client, _ = client_with_cb
    resp = client.get("/api/v1/breakers/phantom")
    assert resp.status_code == 404


# ── POST /api/v1/breakers/{name}/reset ────────────────────────────────────────

def test_post_reset_returns_reset_true(client_with_cb):
    client, _ = client_with_cb
    client.post("/api/v1/breakers", json={"name": "svc"})
    resp = client.post("/api/v1/breakers/svc/reset")
    assert resp.status_code == 200
    assert resp.json()["reset"] is True


def test_post_reset_unknown_404(client_with_cb):
    client, _ = client_with_cb
    resp = client.post("/api/v1/breakers/phantom/reset")
    assert resp.status_code == 404


# ── count after multiple POSTs ────────────────────────────────────────────────

def test_count_two_after_two_posts(client_with_cb):
    client, _ = client_with_cb
    client.post("/api/v1/breakers", json={"name": "a"})
    client.post("/api/v1/breakers", json={"name": "b"})
    data = client.get("/api/v1/breakers").json()
    assert data["count"] == 2
