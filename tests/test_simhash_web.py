"""Phase 89 — tests for the /api/v1/simhash endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.simhash import SimHash
from pradyos.sovereign_web import create_app


def make_doc(n=600, prefix="word"):
    return [f"{prefix}{i}" for i in range(n)]


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app SimHash (num_bits=64) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_det():
    # Deterministic seed=0 store for reproducible Hamming/near-duplicate assertions.
    return TestClient(create_app(simhash=SimHash(num_bits=64, seed=0)))


# ── hash ─────────────────────────────────────────────────────────────────────────

def test_hash_returns_fingerprint(client):
    resp = client.post("/api/v1/simhash/hash", json={"doc": "d", "tokens": ["a", "b", "c"]})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["fingerprint"], int)
    assert body["doc"] == "d"
    assert body["docs"] == 1


def test_hash_missing_doc_returns_422(client):
    assert client.post("/api/v1/simhash/hash", json={"tokens": ["a"]}).status_code == 422


def test_hash_missing_tokens_returns_422(client):
    resp = client.post("/api/v1/simhash/hash", json={"doc": "d"})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_hash_non_list_tokens_returns_422(client):
    assert client.post("/api/v1/simhash/hash",
                       json={"doc": "d", "tokens": "nope"}).status_code == 422


def test_hash_non_dict_body_returns_422(client):
    assert client.post("/api/v1/simhash/hash", json=["nope"]).status_code == 422


# ── similarity ───────────────────────────────────────────────────────────────────

def test_similarity_identical_is_one(client_det):
    client_det.post("/api/v1/simhash/hash", json={"doc": "A", "tokens": make_doc()})
    client_det.post("/api/v1/simhash/hash", json={"doc": "B", "tokens": make_doc()})
    body = client_det.get("/api/v1/simhash/similarity", params={"a": "A", "b": "B"}).json()
    assert body["similarity"] == 1.0


def test_similarity_self_is_one(client):
    client.post("/api/v1/simhash/hash", json={"doc": "A", "tokens": make_doc(50)})
    assert client.get("/api/v1/simhash/similarity",
                      params={"a": "A", "b": "A"}).json()["similarity"] == 1.0


def test_similarity_missing_query_param_returns_422(client):
    assert client.get("/api/v1/simhash/similarity", params={"a": "A"}).status_code == 422


def test_similarity_unknown_document_returns_404(client):
    client.post("/api/v1/simhash/hash", json={"doc": "A", "tokens": ["x"]})
    assert client.get("/api/v1/simhash/similarity",
                      params={"a": "A", "b": "ghost"}).status_code == 404


# ── hamming ──────────────────────────────────────────────────────────────────────

def test_hamming_identical_is_zero(client_det):
    client_det.post("/api/v1/simhash/hash", json={"doc": "A", "tokens": make_doc()})
    client_det.post("/api/v1/simhash/hash", json={"doc": "B", "tokens": make_doc()})
    body = client_det.get("/api/v1/simhash/hamming", params={"a": "A", "b": "B"}).json()
    assert body["hamming"] == 0
    assert body["near_duplicate"] is True


def test_hamming_different_docs_near_half(client_det):
    client_det.post("/api/v1/simhash/hash", json={"doc": "A", "tokens": make_doc()})
    client_det.post("/api/v1/simhash/hash", json={"doc": "B", "tokens": make_doc(prefix="other")})
    body = client_det.get("/api/v1/simhash/hamming", params={"a": "A", "b": "B"}).json()
    assert 20 <= body["hamming"] <= 44
    assert body["near_duplicate"] is False


def test_hamming_unknown_document_returns_404(client):
    client.post("/api/v1/simhash/hash", json={"doc": "A", "tokens": ["x"]})
    assert client.get("/api/v1/simhash/hamming",
                      params={"a": "A", "b": "ghost"}).status_code == 404


def test_hamming_missing_query_param_returns_422(client):
    assert client.get("/api/v1/simhash/hamming", params={"b": "B"}).status_code == 422


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/simhash/stats").json()
    assert set(data) == {"num_bits", "docs", "total_hashed", "seed"}


def test_stats_tracks_docs_and_total(client):
    client.post("/api/v1/simhash/hash", json={"doc": "a", "tokens": ["x"]})
    client.post("/api/v1/simhash/hash", json={"doc": "b", "tokens": ["y"]})
    data = client.get("/api/v1/simhash/stats").json()
    assert data["docs"] == 2 and data["total_hashed"] == 2


def test_stats_default_num_bits(client):
    assert client.get("/api/v1/simhash/stats").json()["num_bits"] == 64


# ── reset ────────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/simhash/hash", json={"doc": "a", "tokens": ["x"]})
    resp = client.post("/api/v1/simhash/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["docs"] == 0 and resp.json()["total_hashed"] == 0


def test_reset_reconfigures_num_bits(client):
    resp = client.post("/api/v1/simhash/reset", json={"num_bits": 128})
    assert resp.json()["num_bits"] == 128


def test_reset_bad_num_bits_returns_422(client):
    assert client.post("/api/v1/simhash/reset", json={"num_bits": 0}).status_code == 422


# ── deterministic near-duplicate over HTTP ───────────────────────────────────────

def test_deterministic_near_duplicate_over_http(client_det):
    base = make_doc()
    near = base[:]
    near[0] = "CHANGED"
    client_det.post("/api/v1/simhash/hash", json={"doc": "base", "tokens": base})
    client_det.post("/api/v1/simhash/hash", json={"doc": "near", "tokens": near})
    body = client_det.get("/api/v1/simhash/hamming", params={"a": "base", "b": "near"}).json()
    assert body["hamming"] <= 3
    assert body["near_duplicate"] is True


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_hash_compare_reset_round_trip(client):
    client.post("/api/v1/simhash/hash", json={"doc": "A", "tokens": make_doc(50)})
    client.post("/api/v1/simhash/hash", json={"doc": "B", "tokens": make_doc(50)})
    assert client.get("/api/v1/simhash/hamming", params={"a": "A", "b": "B"}).json()["hamming"] == 0
    client.post("/api/v1/simhash/reset", json={})
    assert client.get("/api/v1/simhash/stats").json()["docs"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–88 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
    assert client.get("/api/v1/reservoir/stats").status_code == 200
    assert client.get("/api/v1/cuckoo/stats").status_code == 200
    assert client.get("/api/v1/topk/stats").status_code == 200
    assert client.get("/api/v1/minhash/stats").status_code == 200
