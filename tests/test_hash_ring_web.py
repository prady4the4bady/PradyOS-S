"""Phase 73 — tests for the /api/v1/hashring endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.hash_ring import HashRing
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_ring():
    return TestClient(create_app())


@pytest.fixture()
def client_with_ring():
    return TestClient(create_app(hash_ring=HashRing(replicas=50)))


# ── no ring configured ────────────────────────────────────────────────────────

def test_stats_no_ring_returns_error(client_no_ring):
    assert "error" in client_no_ring.get("/api/v1/hashring").json()


def test_add_no_ring_returns_error(client_no_ring):
    assert "error" in client_no_ring.post("/api/v1/hashring/nodes", json={"node": "A"}).json()


def test_get_node_no_ring_returns_error(client_no_ring):
    assert "error" in client_no_ring.get("/api/v1/hashring/node/x").json()


def test_remove_no_ring_returns_error(client_no_ring):
    assert "error" in client_no_ring.delete("/api/v1/hashring/nodes/A").json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_keys(client_with_ring):
    data = client_with_ring.get("/api/v1/hashring").json()
    for key in ("nodes", "node_count", "replicas", "virtual_points"):
        assert key in data


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_node(client_with_ring):
    resp = client_with_ring.post("/api/v1/hashring/nodes", json={"node": "A"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] is True
    assert "A" in body["nodes"]


def test_add_missing_node_returns_422(client_with_ring):
    resp = client_with_ring.post("/api/v1/hashring/nodes", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_add_multiple_updates_node_count(client_with_ring):
    for node in ("A", "B", "C"):
        client_with_ring.post("/api/v1/hashring/nodes", json={"node": node})
    assert client_with_ring.get("/api/v1/hashring").json()["node_count"] == 3


# ── lookup ────────────────────────────────────────────────────────────────────

def test_get_node_empty_ring_returns_none(client_with_ring):
    assert client_with_ring.get("/api/v1/hashring/node/anykey").json()["node"] is None


def test_get_node_returns_member(client_with_ring):
    for node in ("A", "B", "C"):
        client_with_ring.post("/api/v1/hashring/nodes", json={"node": node})
    data = client_with_ring.get("/api/v1/hashring/node/some-key").json()
    assert data["key"] == "some-key"
    assert data["node"] in {"A", "B", "C"}


def test_get_node_is_deterministic(client_with_ring):
    for node in ("A", "B", "C"):
        client_with_ring.post("/api/v1/hashring/nodes", json={"node": node})
    first = client_with_ring.get("/api/v1/hashring/node/repeatable").json()["node"]
    second = client_with_ring.get("/api/v1/hashring/node/repeatable").json()["node"]
    assert first == second


# ── remove ────────────────────────────────────────────────────────────────────

def test_remove_node(client_with_ring):
    client_with_ring.post("/api/v1/hashring/nodes", json={"node": "A"})
    resp = client_with_ring.delete("/api/v1/hashring/nodes/A")
    assert resp.status_code == 200
    assert resp.json()["removed"] is True
    assert client_with_ring.get("/api/v1/hashring").json()["nodes"] == []


def test_remove_unknown_returns_404(client_with_ring):
    resp = client_with_ring.delete("/api/v1/hashring/nodes/ghost")
    assert resp.status_code == 404
    assert "error" in resp.json()
