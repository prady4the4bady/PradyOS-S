"""Phase 91 — tests for the /api/v1/quantile endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.gk_quantile import GKSummary
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app GKSummary (epsilon=0.01) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_det():
    # Deterministic summary for reproducible quantile assertions over HTTP.
    return TestClient(create_app(gk_quantile=GKSummary(epsilon=0.01, seed=0)))


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_single_value(client):
    resp = client.post("/api/v1/quantile/insert", json={"value": 3.5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] == 1
    assert body["n"] == 1


def test_insert_values_list(client):
    resp = client.post("/api/v1/quantile/insert", json={"values": [1, 2, 3, 4, 5]})
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 5
    assert resp.json()["n"] == 5


def test_insert_missing_returns_422(client):
    resp = client.post("/api/v1/quantile/insert", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_insert_non_dict_body_returns_422(client):
    assert client.post("/api/v1/quantile/insert", json=[1, 2]).status_code == 422


def test_insert_non_list_values_returns_422(client):
    assert client.post("/api/v1/quantile/insert", json={"values": "nope"}).status_code == 422


def test_insert_non_number_returns_422(client):
    assert client.post("/api/v1/quantile/insert", json={"value": "abc"}).status_code == 422


# ── query ───────────────────────────────────────────────────────────────────────

def test_query_returns_quantile(client):
    client.post("/api/v1/quantile/insert", json={"values": list(range(1, 101))})
    body = client.get("/api/v1/quantile/query", params={"phi": 0.5}).json()
    assert "quantile" in body
    assert body["phi"] == 0.5


def test_query_median_accuracy(client_det):
    client_det.post("/api/v1/quantile/insert", json={"values": list(range(1, 1001))})
    est = client_det.get("/api/v1/quantile/query", params={"phi": 0.5}).json()["quantile"]
    assert abs(est - 500) <= 0.01 * 1000 + 1


def test_query_extremes(client_det):
    client_det.post("/api/v1/quantile/insert", json={"values": list(range(1, 1001))})
    assert client_det.get("/api/v1/quantile/query", params={"phi": 0.0}).json()["quantile"] == 1
    assert client_det.get("/api/v1/quantile/query", params={"phi": 1.0}).json()["quantile"] == 1000


def test_query_empty_summary_returns_422(client):
    resp = client.get("/api/v1/quantile/query", params={"phi": 0.5})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_query_phi_below_zero_returns_422(client):
    client.post("/api/v1/quantile/insert", json={"value": 1})
    assert client.get("/api/v1/quantile/query", params={"phi": -0.1}).status_code == 422


def test_query_phi_above_one_returns_422(client):
    client.post("/api/v1/quantile/insert", json={"value": 1})
    assert client.get("/api/v1/quantile/query", params={"phi": 1.5}).status_code == 422


def test_query_missing_phi_returns_422(client):
    assert client.get("/api/v1/quantile/query").status_code == 422


# ── count ───────────────────────────────────────────────────────────────────────

def test_count(client):
    client.post("/api/v1/quantile/insert", json={"values": list(range(20))})
    assert client.get("/api/v1/quantile/count").json()["count"] == 20


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/quantile/stats").json()
    assert set(data) == {"epsilon", "n", "summary_size", "capacity"}


def test_stats_tracks_n(client):
    client.post("/api/v1/quantile/insert", json={"values": list(range(123))})
    assert client.get("/api/v1/quantile/stats").json()["n"] == 123


def test_stats_default_epsilon(client):
    assert client.get("/api/v1/quantile/stats").json()["epsilon"] == 0.01


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/quantile/insert", json={"values": list(range(100))})
    resp = client.post("/api/v1/quantile/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["n"] == 0


def test_reset_reconfigures_epsilon(client):
    resp = client.post("/api/v1/quantile/reset", json={"epsilon": 0.05})
    assert resp.json()["epsilon"] == 0.05


def test_reset_bad_epsilon_returns_422(client):
    assert client.post("/api/v1/quantile/reset", json={"epsilon": 0}).status_code == 422


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_insert_query_reset_round_trip(client):
    client.post("/api/v1/quantile/insert", json={"values": list(range(1, 1001))})
    assert client.get("/api/v1/quantile/query", params={"phi": 0.9}).json()["quantile"] >= 850
    client.post("/api/v1/quantile/reset", json={})
    assert client.get("/api/v1/quantile/count").json()["count"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–90 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
    assert client.get("/api/v1/reservoir/stats").status_code == 200
    assert client.get("/api/v1/cuckoo/stats").status_code == 200
    assert client.get("/api/v1/topk/stats").status_code == 200
    assert client.get("/api/v1/minhash/stats").status_code == 200
    assert client.get("/api/v1/simhash/stats").status_code == 200
    assert client.get("/api/v1/quotient/stats").status_code == 200
