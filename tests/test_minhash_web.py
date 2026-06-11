"""Phase 88 — tests for the /api/v1/minhash endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.minhash import MinHash
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app MinHash (num_hashes=128) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_det():
    # Deterministic 256-hash store (seed=7) for accuracy/equality assertions over HTTP.
    return TestClient(create_app(minhash=MinHash(num_hashes=256, seed=7)))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_single_element(client):
    resp = client.post("/api/v1/minhash/add", json={"set": "S", "element": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["set"] == "S"
    assert body["added"] == 1
    assert body["sets"] == 1


def test_add_elements_list(client):
    resp = client.post("/api/v1/minhash/add", json={"set": "S", "elements": [1, 2, 3]})
    assert resp.status_code == 200
    assert resp.json()["added"] == 3


def test_add_missing_set_returns_422(client):
    assert client.post("/api/v1/minhash/add", json={"element": "x"}).status_code == 422


def test_add_missing_element_returns_422(client):
    resp = client.post("/api/v1/minhash/add", json={"set": "S"})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_add_non_dict_body_returns_422(client):
    assert client.post("/api/v1/minhash/add", json=["nope"]).status_code == 422


def test_add_non_list_elements_returns_422(client):
    assert client.post("/api/v1/minhash/add",
                       json={"set": "S", "elements": "nope"}).status_code == 422


# ── similarity ───────────────────────────────────────────────────────────────────

def test_similarity_self_is_one(client):
    client.post("/api/v1/minhash/add", json={"set": "S", "elements": list(range(50))})
    body = client.get("/api/v1/minhash/similarity", params={"a": "S", "b": "S"}).json()
    assert body["similarity"] == 1.0


def test_similarity_identical_content_is_one(client_det):
    client_det.post("/api/v1/minhash/add", json={"set": "A", "elements": list(range(50))})
    client_det.post("/api/v1/minhash/add", json={"set": "B", "elements": list(range(50))})
    assert client_det.get("/api/v1/minhash/similarity",
                          params={"a": "A", "b": "B"}).json()["similarity"] == 1.0


def test_similarity_missing_set_is_zero(client):
    client.post("/api/v1/minhash/add", json={"set": "S", "element": "x"})
    body = client.get("/api/v1/minhash/similarity", params={"a": "S", "b": "ghost"}).json()
    assert body["similarity"] == 0.0


def test_similarity_missing_query_param_returns_422(client):
    assert client.get("/api/v1/minhash/similarity", params={"a": "S"}).status_code == 422


def test_similarity_disjoint_is_low(client_det):
    client_det.post("/api/v1/minhash/add", json={"set": "L", "elements": list(range(0, 400))})
    client_det.post("/api/v1/minhash/add", json={"set": "R", "elements": list(range(9000, 9400))})
    assert client_det.get("/api/v1/minhash/similarity",
                          params={"a": "L", "b": "R"}).json()["similarity"] < 0.05


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/minhash/stats").json()
    assert set(data) == {"num_hashes", "sets", "total_added", "seed"}


def test_stats_tracks_sets_and_total(client):
    client.post("/api/v1/minhash/add", json={"set": "a", "elements": [1, 2, 3]})
    client.post("/api/v1/minhash/add", json={"set": "b", "element": 4})
    data = client.get("/api/v1/minhash/stats").json()
    assert data["sets"] == 2 and data["total_added"] == 4


def test_stats_default_num_hashes(client):
    assert client.get("/api/v1/minhash/stats").json()["num_hashes"] == 128


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/minhash/add", json={"set": "a", "elements": [1, 2, 3]})
    resp = client.post("/api/v1/minhash/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["sets"] == 0 and resp.json()["total_added"] == 0


def test_reset_reconfigures_num_hashes(client):
    resp = client.post("/api/v1/minhash/reset", json={"num_hashes": 32})
    assert resp.json()["num_hashes"] == 32


def test_reset_bad_num_hashes_returns_422(client):
    assert client.post("/api/v1/minhash/reset", json={"num_hashes": 0}).status_code == 422


# ── deterministic Jaccard over HTTP ──────────────────────────────────────────────

def test_deterministic_similarity_estimate_over_http(client_det):
    # true Jaccard of [0,600) and [300,900) = 300/900 = 1/3; 256 hashes ⇒ close estimate
    client_det.post("/api/v1/minhash/add", json={"set": "A", "elements": list(range(0, 600))})
    client_det.post("/api/v1/minhash/add", json={"set": "B", "elements": list(range(300, 900))})
    est = client_det.get("/api/v1/minhash/similarity",
                         params={"a": "A", "b": "B"}).json()["similarity"]
    assert abs(est - 1 / 3) < 0.08


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_add_similarity_reset_round_trip(client):
    client.post("/api/v1/minhash/add", json={"set": "A", "elements": [1, 2, 3]})
    client.post("/api/v1/minhash/add", json={"set": "B", "elements": [1, 2, 3]})
    assert client.get("/api/v1/minhash/similarity",
                      params={"a": "A", "b": "B"}).json()["similarity"] == 1.0
    client.post("/api/v1/minhash/reset", json={})
    assert client.get("/api/v1/minhash/stats").json()["sets"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–87 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
    assert client.get("/api/v1/reservoir/stats").status_code == 200
    assert client.get("/api/v1/cuckoo/stats").status_code == 200
    assert client.get("/api/v1/topk/stats").status_code == 200
