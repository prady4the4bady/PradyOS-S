"""Phase 93 — tests for the /api/v1/theta endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.theta_sketch import ThetaSketch
from pradyos.sovereign_web import create_app


def distinct(prefix, n, start=0):
    return [f"{prefix}{i}" for i in range(start, start + n)]


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app ThetaSketch (k=4096) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_det():
    # Deterministic sketch for reproducible cardinality assertions over HTTP.
    return TestClient(create_app(theta=ThetaSketch(k=4096, seed=0)))


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_single_element(client):
    resp = client.post("/api/v1/theta/insert", json={"element": "a"})
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 1 and resp.json()["n"] == 1


def test_insert_elements_list(client):
    resp = client.post("/api/v1/theta/insert", json={"elements": ["a", "b", "c"]})
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 3 and resp.json()["n"] == 3


def test_insert_missing_returns_422(client):
    resp = client.post("/api/v1/theta/insert", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_insert_non_dict_body_returns_422(client):
    assert client.post("/api/v1/theta/insert", json=["a"]).status_code == 422


def test_insert_non_list_elements_returns_422(client):
    assert client.post("/api/v1/theta/insert", json={"elements": "nope"}).status_code == 422


# ── estimate ────────────────────────────────────────────────────────────────────

def test_estimate_accuracy(client_det):
    client_det.post("/api/v1/theta/insert", json={"elements": distinct("item-", 10_000)})
    est = client_det.get("/api/v1/theta/estimate").json()["estimate"]
    assert abs(est - 10_000) / 10_000 < 0.05


def test_estimate_empty_is_zero(client):
    body = client.get("/api/v1/theta/estimate").json()
    assert body["estimate"] == 0 and body["is_exact"] is True


def test_estimate_duplicates_dont_inflate(client):
    client.post("/api/v1/theta/insert", json={"elements": ["same"] * 5000})
    assert client.get("/api/v1/theta/estimate").json()["estimate"] == 1


def test_estimate_exact_regime(client):
    client.post("/api/v1/theta/insert", json={"elements": distinct("e", 100)})
    body = client.get("/api/v1/theta/estimate").json()
    assert body["estimate"] == 100 and body["is_exact"] is True


# ── merge (union / intersection) ─────────────────────────────────────────────────

def test_merge_union(client_det):
    client_det.post("/api/v1/theta/insert", json={"elements": distinct("s", 5000, start=0)})
    resp = client_det.post("/api/v1/theta/merge", params={"op": "union"},
                           json={"values": distinct("s", 5000, start=5000)})
    assert resp.status_code == 200
    assert resp.json()["op"] == "union"
    assert abs(resp.json()["estimate"] - 10_000) / 10_000 < 0.05


def test_merge_default_op_is_union(client_det):
    client_det.post("/api/v1/theta/insert", json={"elements": distinct("s", 3000)})
    resp = client_det.post("/api/v1/theta/merge", json={"values": distinct("s", 3000, start=3000)})
    assert resp.json()["op"] == "union"
    assert resp.json()["estimate"] > 5000


def test_merge_intersection(client_det):
    client_det.post("/api/v1/theta/insert", json={"elements": distinct("x", 5000, start=0)})
    resp = client_det.post("/api/v1/theta/merge", params={"op": "intersection"},
                           json={"values": distinct("x", 5000, start=2500)})
    assert resp.json()["op"] == "intersection"
    assert abs(resp.json()["estimate"] - 2500) / 2500 < 0.10


def test_merge_intersection_is_non_destructive(client_det):
    client_det.post("/api/v1/theta/insert", json={"elements": distinct("x", 5000, start=0)})
    before = client_det.get("/api/v1/theta/estimate").json()["estimate"]
    client_det.post("/api/v1/theta/merge", params={"op": "intersection"},
                    json={"values": distinct("x", 5000, start=2500)})
    after = client_det.get("/api/v1/theta/estimate").json()["estimate"]
    assert after == before                     # the shared sketch is untouched


def test_merge_invalid_op_returns_422(client):
    resp = client.post("/api/v1/theta/merge", params={"op": "bogus"}, json={"values": [1]})
    assert resp.status_code == 422


def test_merge_missing_values_returns_422(client):
    assert client.post("/api/v1/theta/merge", json={}).status_code == 422


def test_merge_non_list_values_returns_422(client):
    assert client.post("/api/v1/theta/merge", json={"values": "nope"}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/theta/stats").json()
    assert set(data) == {"k", "n", "theta", "retained_count", "is_exact", "estimate"}


def test_stats_tracks_inserts(client):
    client.post("/api/v1/theta/insert", json={"elements": distinct("s", 500)})
    data = client.get("/api/v1/theta/stats").json()
    assert data["n"] == 500 and data["retained_count"] == 500 and data["is_exact"] is True


def test_stats_default_k(client):
    assert client.get("/api/v1/theta/stats").json()["k"] == 4096


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/theta/insert", json={"elements": distinct("s", 1000)})
    resp = client.post("/api/v1/theta/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["n"] == 0 and resp.json()["estimate"] == 0


def test_reset_reconfigures_k(client):
    resp = client.post("/api/v1/theta/reset", json={"k": 256})
    assert resp.json()["k"] == 256


def test_reset_bad_k_returns_422(client):
    assert client.post("/api/v1/theta/reset", json={"k": 1}).status_code == 422


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_insert_estimate_reset_round_trip(client):
    client.post("/api/v1/theta/insert", json={"elements": distinct("r", 5000)})
    assert client.get("/api/v1/theta/estimate").json()["estimate"] > 4000
    client.post("/api/v1/theta/reset", json={})
    assert client.get("/api/v1/theta/estimate").json()["estimate"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–92 routes still respond
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
