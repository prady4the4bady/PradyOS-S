"""Phase 84 — tests for the /api/v1/lru endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.lru_cache import SovereignLRUCache
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app SovereignLRUCache inside the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_small():
    return TestClient(create_app(lru_cache=SovereignLRUCache(2)))


# ── PUT ───────────────────────────────────────────────────────────────────────

def test_put_returns_key_value_size(client):
    resp = client.put("/api/v1/lru/a", json={"value": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] == "a"
    assert body["value"] == 1
    assert body["size"] == 1


def test_put_with_ttl_echoes_ttl(client):
    resp = client.put("/api/v1/lru/a", json={"value": 1, "ttl": 30})
    assert resp.json()["ttl"] == 30


def test_put_bad_ttl_returns_422(client):
    assert client.put("/api/v1/lru/a", json={"value": 1, "ttl": -5}).status_code == 422


def test_put_updates_existing(client):
    client.put("/api/v1/lru/a", json={"value": 1})
    client.put("/api/v1/lru/a", json={"value": 2})
    assert client.get("/api/v1/lru/a").json()["value"] == 2


# ── GET ───────────────────────────────────────────────────────────────────────

def test_get_found(client):
    client.put("/api/v1/lru/a", json={"value": 99})
    body = client.get("/api/v1/lru/a").json()
    assert body["found"] is True
    assert body["value"] == 99


def test_get_miss_returns_404(client):
    resp = client.get("/api/v1/lru/ghost")
    assert resp.status_code == 404
    assert resp.json()["found"] is False


# ── DELETE ────────────────────────────────────────────────────────────────────

def test_delete_existing(client):
    client.put("/api/v1/lru/a", json={"value": 1})
    resp = client.delete("/api/v1/lru/a")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert client.get("/api/v1/lru/a").status_code == 404


def test_delete_absent_returns_404(client):
    resp = client.delete("/api/v1/lru/ghost")
    assert resp.status_code == 404
    assert resp.json()["deleted"] is False


# ── snapshot ──────────────────────────────────────────────────────────────────

def test_snapshot_structure(client):
    client.put("/api/v1/lru/a", json={"value": 1})
    body = client.get("/api/v1/lru/snapshot").json()
    assert set(body) == {"capacity", "size", "entries"}


def test_snapshot_most_recent_first(client):
    for k in ("a", "b", "c"):
        client.put(f"/api/v1/lru/{k}", json={"value": k})
    entries = client.get("/api/v1/lru/snapshot").json()["entries"]
    assert [e[0] for e in entries] == ["c", "b", "a"]


def test_snapshot_route_not_shadowed_by_key(client):
    # GET /api/v1/lru/snapshot must hit the snapshot route (200 + entries),
    # not the /{key} route as a miss for key "snapshot".
    resp = client.get("/api/v1/lru/snapshot")
    assert resp.status_code == 200
    assert "entries" in resp.json()


# ── resize ────────────────────────────────────────────────────────────────────

def test_resize_changes_capacity(client):
    resp = client.post("/api/v1/lru/resize", json={"capacity": 5})
    assert resp.status_code == 200
    assert resp.json()["capacity"] == 5


def test_resize_bad_capacity_returns_422(client):
    assert client.post("/api/v1/lru/resize", json={"capacity": 0}).status_code == 422


def test_resize_smaller_evicts(client_small):
    # capacity 2; insert 2, then shrink to 1 → one survives
    client_small.put("/api/v1/lru/a", json={"value": 1})
    client_small.put("/api/v1/lru/b", json={"value": 2})
    client_small.post("/api/v1/lru/resize", json={"capacity": 1})
    assert client_small.get("/api/v1/lru/snapshot").json()["size"] == 1


# ── eviction ──────────────────────────────────────────────────────────────────

def test_eviction_over_capacity(client_small):
    for k in ("a", "b", "c"):           # capacity 2 → 'a' evicted
        client_small.put(f"/api/v1/lru/{k}", json={"value": k})
    assert client_small.get("/api/v1/lru/a").status_code == 404
    assert client_small.get("/api/v1/lru/c").status_code == 200


# ── TTL expiry (deterministic via injected clock) ─────────────────────────────

def test_ttl_expiry_over_http():
    clock = type("Clk", (), {"t": 0.0, "__call__": lambda self: self.t})()
    client = TestClient(create_app(lru_cache=SovereignLRUCache(5, time_fn=clock)))
    client.put("/api/v1/lru/k", json={"value": "v", "ttl": 10})
    clock.t = 5
    assert client.get("/api/v1/lru/k").json()["value"] == "v"
    clock.t = 11
    assert client.get("/api/v1/lru/k").status_code == 404


# ── round-trip / regression ───────────────────────────────────────────────────

def test_put_get_delete_round_trip(client):
    client.put("/api/v1/lru/x", json={"value": 7})
    assert client.get("/api/v1/lru/x").json()["value"] == 7
    client.delete("/api/v1/lru/x")
    assert client.get("/api/v1/lru/x").status_code == 404


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # the Phase 83 trie route still responds (404 for an absent key — route live)
    assert client.get("/api/v1/trie/anykey").status_code == 404
