"""Plane 8 — tests for the /api/v1/quasar endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.quasar_gate import QuasarGate
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def pooled_client():
    gate = QuasarGate()
    gate.register("ollama-local", "local", {"code", "chat"}, latency_ms=200, cost=0.0)
    gate.register("frontier-remote", "remote", {"code", "research"}, latency_ms=900, cost=1.0)
    return TestClient(create_app(quasar=gate))


# ── registration ──────────────────────────────────────────────────────────────


def test_register_backend(client):
    resp = client.post(
        "/api/v1/quasar/backend",
        json={"name": "b1", "location": "local", "capabilities": ["code"], "latency_ms": 100},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "b1" and body["location"] == "local" and body["healthy"] is True


def test_register_missing_field_422(client):
    resp = client.post("/api/v1/quasar/backend", json={"name": "b1"})
    assert resp.status_code == 422 and "error" in resp.json()


def test_register_bad_location_422(client):
    resp = client.post(
        "/api/v1/quasar/backend",
        json={"name": "b", "location": "edge", "capabilities": ["code"], "latency_ms": 1},
    )
    assert resp.status_code == 422


def test_backends_list(pooled_client):
    names = sorted(
        b["name"] for b in pooled_client.get("/api/v1/quasar/backends").json()["backends"]
    )
    assert names == ["frontier-remote", "ollama-local"]


# ── routing ───────────────────────────────────────────────────────────────────


def test_route_local_first(pooled_client):
    body = pooled_client.post("/api/v1/quasar/route", json={"task_class": "code"}).json()
    assert body["routed"] is True and body["backend"]["name"] == "ollama-local"


def test_route_capability(pooled_client):
    body = pooled_client.post("/api/v1/quasar/route", json={"task_class": "research"}).json()
    assert body["backend"]["name"] == "frontier-remote"


def test_route_local_only_no_route_409(pooled_client):
    resp = pooled_client.post(
        "/api/v1/quasar/route", json={"task_class": "research", "local_only": True}
    )
    assert resp.status_code == 409 and resp.json()["routed"] is False


def test_route_missing_task_class_422(client):
    assert client.post("/api/v1/quasar/route", json={}).status_code == 422


def test_route_bad_priority_422(pooled_client):
    resp = pooled_client.post(
        "/api/v1/quasar/route", json={"task_class": "code", "priority": "urgent"}
    )
    assert resp.status_code == 422


def test_candidates_chain(pooled_client):
    body = pooled_client.get("/api/v1/quasar/candidates", params={"task_class": "code"}).json()
    assert body["candidates"] == ["ollama-local", "frontier-remote"]


# ── health & fallback ─────────────────────────────────────────────────────────


def test_health_toggle_falls_back(pooled_client):
    pooled_client.post("/api/v1/quasar/health", json={"name": "ollama-local", "healthy": False})
    body = pooled_client.post("/api/v1/quasar/route", json={"task_class": "code"}).json()
    assert body["backend"]["name"] == "frontier-remote"


def test_health_unknown_backend_404(client):
    resp = client.post("/api/v1/quasar/health", json={"name": "nope", "healthy": False})
    assert resp.status_code == 404


# ── stats & reset ─────────────────────────────────────────────────────────────


def test_stats_and_reset(pooled_client):
    pooled_client.post("/api/v1/quasar/route", json={"task_class": "code"})
    stats = pooled_client.get("/api/v1/quasar/stats").json()
    assert stats["routes"] == 1 and stats["backends"] == 2
    after = pooled_client.delete("/api/v1/quasar/reset").json()
    assert after["routes"] == 0 and after["backends"] == 0
