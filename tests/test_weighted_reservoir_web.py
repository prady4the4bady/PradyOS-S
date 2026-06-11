"""Phase 98 — tests for the /api/v1/sample endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.weighted_reservoir import WeightedReservoir
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app WeightedReservoir (k=100) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def full_client():
    # A pre-built reservoir at capacity (k=50, 10k uniform items) injected into the factory.
    wr = WeightedReservoir(50, seed=0)
    for i in range(10_000):
        wr.update(f"x{i}", 1.0)
    return TestClient(create_app(weighted_reservoir=wr))


@pytest.fixture()
def biased_client():
    # One very heavy item amid many light ones, k=5 → the heavy item is (almost) certain.
    wr = WeightedReservoir(5, seed=0)
    wr.update("HEAVY", 1000.0)
    for i in range(100):
        wr.update(f"light{i}", 1.0)
    return TestClient(create_app(weighted_reservoir=wr))


# ── update ──────────────────────────────────────────────────────────────────────

def test_update_single(client):
    resp = client.post("/api/v1/sample/update", params={"item": "a"})
    assert resp.status_code == 200
    assert resp.json()["n"] == 1 and resp.json()["size"] == 1


def test_update_with_weight(client):
    resp = client.post("/api/v1/sample/update", params={"item": "a", "weight": 2.5})
    assert resp.status_code == 200
    assert resp.json()["weight"] == 2.5


def test_update_missing_item_returns_422(client):
    assert client.post("/api/v1/sample/update", params={"weight": 1}).status_code == 422


def test_update_zero_weight_returns_422(client):
    assert client.post("/api/v1/sample/update", params={"item": "a", "weight": 0}).status_code == 422


def test_update_negative_weight_returns_422(client):
    assert client.post("/api/v1/sample/update", params={"item": "a", "weight": -1}).status_code == 422


def test_update_returns_n_and_size(client):
    for i in range(5):
        client.post("/api/v1/sample/update", params={"item": f"x{i}"})
    body = client.post("/api/v1/sample/update", params={"item": "x5"}).json()
    assert body["n"] == 6 and body["size"] == 6


# ── sample ──────────────────────────────────────────────────────────────────────

def test_sample_empty(client):
    body = client.get("/api/v1/sample/sample").json()
    assert body["items"] == [] and body["n"] == 0 and body["k"] == 100


def test_sample_returns_items(client):
    for i in range(10):
        client.post("/api/v1/sample/update", params={"item": f"x{i}"})
    body = client.get("/api/v1/sample/sample").json()
    assert len(body["items"]) == 10 and body["n"] == 10


def test_sample_structure(client):
    client.post("/api/v1/sample/update", params={"item": "a"})
    assert set(client.get("/api/v1/sample/sample").json()) == {"items", "n", "k"}


def test_sample_capacity(full_client):
    body = full_client.get("/api/v1/sample/sample").json()
    assert len(body["items"]) == 50 and body["n"] == 10_000 and body["k"] == 50


def test_high_weight_item_retained(biased_client):
    items = biased_client.get("/api/v1/sample/sample").json()["items"]
    assert "HEAVY" in items                     # weight 1000 vs 1 → almost certainly kept


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/sample/stats").json()) == {"k", "n", "size", "seed"}


def test_stats_tracks(client):
    for i in range(20):
        client.post("/api/v1/sample/update", params={"item": f"x{i}"})
    data = client.get("/api/v1/sample/stats").json()
    assert data["n"] == 20 and data["size"] == 20


def test_stats_default_k(client):
    assert client.get("/api/v1/sample/stats").json()["k"] == 100


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    for i in range(50):
        client.post("/api/v1/sample/update", params={"item": f"x{i}"})
    resp = client.post("/api/v1/sample/reset")
    assert resp.status_code == 200
    assert resp.json()["n"] == 0 and resp.json()["size"] == 0


def test_reset_then_refill(client):
    for i in range(30):
        client.post("/api/v1/sample/update", params={"item": f"x{i}"})
    client.post("/api/v1/sample/reset")
    for i in range(10):
        client.post("/api/v1/sample/update", params={"item": f"y{i}"})
    body = client.get("/api/v1/sample/sample").json()
    assert body["n"] == 10 and len(body["items"]) == 10


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_update_sample_reset_round_trip(client):
    for i in range(40):
        client.post("/api/v1/sample/update", params={"item": f"r{i}"})
    assert len(client.get("/api/v1/sample/sample").json()["items"]) == 40
    client.post("/api/v1/sample/reset")
    assert client.get("/api/v1/sample/sample").json()["items"] == []


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–97 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
    assert client.get("/api/v1/reservoir/stats").status_code == 200
    assert client.get("/api/v1/cuckoo/stats").status_code == 200
    assert client.get("/api/v1/topk/stats").status_code == 200
    assert client.get("/api/v1/minhash/stats").status_code == 200
    assert client.get("/api/v1/simhash/stats").status_code == 200
    assert client.get("/api/v1/quotient/stats").status_code == 200
    assert client.get("/api/v1/quantile/stats").status_code == 200
    assert client.get("/api/v1/kll/stats").status_code == 200
    assert client.get("/api/v1/theta/stats").status_code == 200
    assert client.get("/api/v1/countsketch/stats").status_code == 200
    assert client.get("/api/v1/lossycount/stats").status_code == 200
    assert client.get("/api/v1/ddsketch/stats").status_code == 200
    assert client.get("/api/v1/window/stats").status_code == 200
