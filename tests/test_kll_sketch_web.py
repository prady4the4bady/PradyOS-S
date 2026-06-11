"""Phase 92 — tests for the /api/v1/kll endpoints in sovereign_web."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.kll_sketch import KLLSketch
from pradyos.sovereign_web import create_app


def uniform(n, seed=0):
    rnd = random.Random(seed)
    return [rnd.random() for _ in range(n)]


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app KLLSketch (k=200) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_det():
    # Deterministic sketch for reproducible quantile assertions over HTTP.
    return TestClient(create_app(kll=KLLSketch(k=200, seed=0)))


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_single_value(client):
    resp = client.post("/api/v1/kll/insert", json={"value": 3.5})
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 1 and resp.json()["n"] == 1


def test_insert_values_list(client):
    resp = client.post("/api/v1/kll/insert", json={"values": [1, 2, 3, 4, 5]})
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 5 and resp.json()["n"] == 5


def test_insert_missing_returns_422(client):
    resp = client.post("/api/v1/kll/insert", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_insert_non_dict_body_returns_422(client):
    assert client.post("/api/v1/kll/insert", json=[1, 2]).status_code == 422


def test_insert_non_list_values_returns_422(client):
    assert client.post("/api/v1/kll/insert", json={"values": "nope"}).status_code == 422


def test_insert_non_number_returns_422(client):
    assert client.post("/api/v1/kll/insert", json={"value": "abc"}).status_code == 422


# ── query ───────────────────────────────────────────────────────────────────────

def test_query_returns_quantile(client):
    client.post("/api/v1/kll/insert", json={"values": list(range(1, 101))})
    body = client.get("/api/v1/kll/query", params={"phi": 0.5}).json()
    assert "quantile" in body and body["phi"] == 0.5


def test_query_median_accuracy(client_det):
    client_det.post("/api/v1/kll/insert", json={"values": uniform(8000, seed=1)})
    est = client_det.get("/api/v1/kll/query", params={"phi": 0.5}).json()["quantile"]
    assert abs(est - 0.5) <= 0.05


def test_query_empty_returns_422(client):
    resp = client.get("/api/v1/kll/query", params={"phi": 0.5})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_query_phi_below_zero_returns_422(client):
    client.post("/api/v1/kll/insert", json={"value": 1})
    assert client.get("/api/v1/kll/query", params={"phi": -0.1}).status_code == 422


def test_query_phi_above_one_returns_422(client):
    client.post("/api/v1/kll/insert", json={"value": 1})
    assert client.get("/api/v1/kll/query", params={"phi": 1.5}).status_code == 422


def test_query_missing_phi_returns_422(client):
    assert client.get("/api/v1/kll/query").status_code == 422


# ── merge (the defining feature) ─────────────────────────────────────────────────

def test_merge_endpoint_median(client_det):
    data = uniform(10_000, seed=2)
    client_det.post("/api/v1/kll/insert", json={"values": data[:5000]})
    resp = client_det.post("/api/v1/kll/merge", json={"values": data[5000:]})
    assert resp.status_code == 200
    assert resp.json()["n"] == 10_000
    est = client_det.get("/api/v1/kll/query", params={"phi": 0.5}).json()["quantile"]
    assert abs(est - 0.5) <= 0.05


def test_merge_combines_counts(client):
    client.post("/api/v1/kll/insert", json={"values": list(range(3000))})
    resp = client.post("/api/v1/kll/merge", json={"values": list(range(3000, 7000))})
    assert resp.json()["merged"] == 4000 and resp.json()["n"] == 7000


def test_merge_missing_values_returns_422(client):
    assert client.post("/api/v1/kll/merge", json={}).status_code == 422


def test_merge_non_list_values_returns_422(client):
    assert client.post("/api/v1/kll/merge", json={"values": "nope"}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/kll/stats").json()
    assert set(data) == {"k", "n", "num_levels", "num_compactors", "sketch_size_ratio"}


def test_stats_tracks_n(client):
    client.post("/api/v1/kll/insert", json={"values": list(range(456))})
    assert client.get("/api/v1/kll/stats").json()["n"] == 456


def test_stats_default_k(client):
    assert client.get("/api/v1/kll/stats").json()["k"] == 200


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/kll/insert", json={"values": list(range(1000))})
    resp = client.post("/api/v1/kll/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["n"] == 0


def test_reset_reconfigures_k(client):
    resp = client.post("/api/v1/kll/reset", json={"k": 64})
    assert resp.json()["k"] == 64


def test_reset_bad_k_returns_422(client):
    assert client.post("/api/v1/kll/reset", json={"k": 1}).status_code == 422


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_insert_query_reset_round_trip(client):
    client.post("/api/v1/kll/insert", json={"values": list(range(1, 1001))})
    assert client.get("/api/v1/kll/query", params={"phi": 0.9}).json()["quantile"] >= 800
    client.post("/api/v1/kll/reset", json={})
    assert client.get("/api/v1/kll/stats").json()["n"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–91 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
    assert client.get("/api/v1/reservoir/stats").status_code == 200
    assert client.get("/api/v1/cuckoo/stats").status_code == 200
    assert client.get("/api/v1/topk/stats").status_code == 200
    assert client.get("/api/v1/minhash/stats").status_code == 200
    assert client.get("/api/v1/simhash/stats").status_code == 200
    assert client.get("/api/v1/quotient/stats").status_code == 200
    assert client.get("/api/v1/quantile/stats").status_code == 200
