"""Phase 85 — tests for the /api/v1/reservoir endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.reservoir import SovereignReservoir
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app SovereignReservoir (cap 16) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_det():
    # Deterministic RNG: decisions for items at i=3,4,5 → reservoir ends [5,1,2].
    seq = iter([0.0, 0.99, 0.0])
    res = SovereignReservoir(3, random_fn=lambda: next(seq))
    return TestClient(create_app(reservoir=res))


# ── feed ──────────────────────────────────────────────────────────────────────

def test_feed_single_item(client):
    resp = client.post("/api/v1/reservoir/feed", json={"item": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["fed"] == 1
    assert body["seen"] == 1
    assert body["filled"] == 1


def test_feed_items_list(client):
    resp = client.post("/api/v1/reservoir/feed", json={"items": list(range(5))})
    assert resp.status_code == 200
    assert resp.json()["fed"] == 5
    assert resp.json()["seen"] == 5


def test_feed_missing_returns_422(client):
    resp = client.post("/api/v1/reservoir/feed", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_feed_non_list_items_returns_422(client):
    assert client.post("/api/v1/reservoir/feed", json={"items": "nope"}).status_code == 422


def test_feed_over_capacity_caps_filled(client):
    client.post("/api/v1/reservoir/feed", json={"items": list(range(100))})
    stats = client.get("/api/v1/reservoir/stats").json()
    assert stats["seen"] == 100
    assert stats["filled"] == stats["capacity"]   # 16


# ── sample ────────────────────────────────────────────────────────────────────

def test_sample_structure(client):
    client.post("/api/v1/reservoir/feed", json={"items": [1, 2, 3]})
    body = client.get("/api/v1/reservoir/sample").json()
    assert set(body) == {"sample", "size"}
    assert body["size"] == 3


def test_sample_empty_initially(client):
    body = client.get("/api/v1/reservoir/sample").json()
    assert body["sample"] == []
    assert body["size"] == 0


def test_sample_reflects_small_stream(client):
    client.post("/api/v1/reservoir/feed", json={"items": [10, 20, 30]})
    assert sorted(client.get("/api/v1/reservoir/sample").json()["sample"]) == [10, 20, 30]


# ── deterministic Algorithm R over HTTP ───────────────────────────────────────

def test_deterministic_reservoir_over_http(client_det):
    client_det.post("/api/v1/reservoir/feed", json={"items": [0, 1, 2, 3, 4, 5]})
    assert client_det.get("/api/v1/reservoir/sample").json()["sample"] == [5, 1, 2]


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/reservoir/stats").json()
    assert set(data) == {"capacity", "seen", "filled"}


def test_stats_tracks_seen(client):
    client.post("/api/v1/reservoir/feed", json={"items": list(range(7))})
    assert client.get("/api/v1/reservoir/stats").json()["seen"] == 7


# ── reset ─────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/reservoir/feed", json={"items": list(range(20))})
    resp = client.post("/api/v1/reservoir/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["seen"] == 0
    assert client.get("/api/v1/reservoir/sample").json()["sample"] == []


def test_reset_resizes_capacity(client):
    resp = client.post("/api/v1/reservoir/reset", json={"capacity": 5})
    assert resp.json()["capacity"] == 5


def test_reset_bad_capacity_returns_422(client):
    assert client.post("/api/v1/reservoir/reset", json={"capacity": 0}).status_code == 422


# ── round-trip / regression ───────────────────────────────────────────────────

def test_feed_sample_reset_round_trip(client):
    client.post("/api/v1/reservoir/feed", json={"items": [1, 2, 3]})
    assert client.get("/api/v1/reservoir/sample").json()["size"] == 3
    client.post("/api/v1/reservoir/reset", json={})
    assert client.get("/api/v1/reservoir/stats").json()["seen"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83/84 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
