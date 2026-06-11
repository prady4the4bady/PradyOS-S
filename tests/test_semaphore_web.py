"""Phase 57D — 10 tests for SemaphoreGate endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.semaphore_gate import SemaphoreGate
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_gate():
    return TestClient(create_app())


@pytest.fixture()
def client_with_gate():
    g = SemaphoreGate()
    app = create_app(semaphore_gate=g)
    return TestClient(app), g


# ── GET /api/v1/semaphores ────────────────────────────────────────────────────

def test_get_returns_200_with_names_count(client_with_gate):
    client, _ = client_with_gate
    data = client.get("/api/v1/semaphores").json()
    assert "names" in data
    assert "count" in data


def test_get_no_gate_empty(client_no_gate):
    data = client_no_gate.get("/api/v1/semaphores").json()
    assert data["names"] == []
    assert data["count"] == 0


# ── POST /api/v1/semaphores ──────────────────────────────────────────────────

def test_post_creates_and_returns_stats(client_with_gate):
    client, _ = client_with_gate
    data = client.post("/api/v1/semaphores",
                       json={"name": "svc", "capacity": 3}).json()
    assert data["name"] == "svc"
    assert data["capacity"] == 3
    assert data["available"] == 3


def test_post_idempotent_same_capacity(client_with_gate):
    client, _ = client_with_gate
    resp1 = client.post("/api/v1/semaphores", json={"name": "svc", "capacity": 2})
    resp2 = client.post("/api/v1/semaphores", json={"name": "svc", "capacity": 2})
    assert resp1.status_code == 200
    assert resp2.status_code == 200


def test_post_capacity_mismatch_returns_409(client_with_gate):
    client, _ = client_with_gate
    client.post("/api/v1/semaphores", json={"name": "svc", "capacity": 2})
    resp = client.post("/api/v1/semaphores", json={"name": "svc", "capacity": 5})
    assert resp.status_code == 409


# ── GET /api/v1/semaphores/{name} ────────────────────────────────────────────

def test_get_by_name_returns_stats(client_with_gate):
    client, _ = client_with_gate
    client.post("/api/v1/semaphores", json={"name": "svc"})
    data = client.get("/api/v1/semaphores/svc").json()
    assert data["name"] == "svc"


def test_get_unknown_returns_404(client_with_gate):
    client, _ = client_with_gate
    resp = client.get("/api/v1/semaphores/phantom")
    assert resp.status_code == 404


# ── acquire / release ────────────────────────────────────────────────────────

def test_acquire_returns_acquired_true(client_with_gate):
    client, _ = client_with_gate
    client.post("/api/v1/semaphores", json={"name": "svc", "capacity": 1})
    data = client.post("/api/v1/semaphores/svc/acquire",
                       json={"timeout": 0}).json()
    assert data["acquired"] is True


def test_release_returns_released_true(client_with_gate):
    client, _ = client_with_gate
    client.post("/api/v1/semaphores", json={"name": "svc", "capacity": 1})
    client.post("/api/v1/semaphores/svc/acquire", json={"timeout": 0})
    data = client.post("/api/v1/semaphores/svc/release").json()
    assert data["released"] is True


# ── acquire on full → false ──────────────────────────────────────────────────

def test_acquire_on_full_returns_false(client_with_gate):
    client, _ = client_with_gate
    client.post("/api/v1/semaphores", json={"name": "svc", "capacity": 1})
    client.post("/api/v1/semaphores/svc/acquire", json={"timeout": 0})
    data = client.post("/api/v1/semaphores/svc/acquire",
                       json={"timeout": 0}).json()
    assert data["acquired"] is False
