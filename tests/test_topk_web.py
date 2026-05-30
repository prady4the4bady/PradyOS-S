"""Phase 87 — tests for the /api/v1/topk endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.space_saving import SpaceSaving
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app SpaceSaving (k=10) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_det():
    # Deterministic k=2 sketch: stream a,b,a,c → {a:(2,0), c:(2,1)}, b evicted.
    return TestClient(create_app(space_saving=SpaceSaving(k=2)))


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_single_item(client):
    resp = client.post("/api/v1/topk/insert", json={"item": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] == 1
    assert body["total"] == 1
    assert body["monitored"] == 1


def test_insert_items_list(client):
    resp = client.post("/api/v1/topk/insert", json={"items": ["a", "b", "a"]})
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 3
    assert resp.json()["total"] == 3
    assert resp.json()["monitored"] == 2


def test_insert_missing_returns_422(client):
    resp = client.post("/api/v1/topk/insert", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_insert_non_dict_body_returns_422(client):
    assert client.post("/api/v1/topk/insert", json=["nope"]).status_code == 422


def test_insert_non_list_items_returns_422(client):
    assert client.post("/api/v1/topk/insert", json={"items": "nope"}).status_code == 422


def test_insert_unhashable_item_returns_422(client):
    resp = client.post("/api/v1/topk/insert", json={"item": ["unhashable"]})
    assert resp.status_code == 422
    assert "error" in resp.json()


# ── query ───────────────────────────────────────────────────────────────────────

def test_query_returns_leaderboard(client):
    client.post("/api/v1/topk/insert", json={"items": ["x"] * 5 + ["y"] * 3 + ["z"]})
    body = client.get("/api/v1/topk/query").json()
    assert [e["item"] for e in body["top"]] == ["x", "y", "z"]
    assert body["n"] == 3


def test_query_n_limits_results(client):
    client.post("/api/v1/topk/insert", json={"items": ["x"] * 5 + ["y"] * 3 + ["z"]})
    body = client.get("/api/v1/topk/query", params={"n": 2}).json()
    assert [e["item"] for e in body["top"]] == ["x", "y"]
    assert body["n"] == 2


def test_query_empty_initially(client):
    body = client.get("/api/v1/topk/query").json()
    assert body["top"] == []
    assert body["n"] == 0


def test_query_negative_n_returns_422(client):
    assert client.get("/api/v1/topk/query", params={"n": -1}).status_code == 422


def test_query_non_int_n_returns_422(client):
    assert client.get("/api/v1/topk/query", params={"n": "abc"}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/topk/stats").json()
    assert set(data) == {"k", "monitored", "total", "min_count"}


def test_stats_tracks_total(client):
    client.post("/api/v1/topk/insert", json={"items": list("aabbbc")})
    assert client.get("/api/v1/topk/stats").json()["total"] == 6


def test_stats_default_k(client):
    assert client.get("/api/v1/topk/stats").json()["k"] == 10


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/topk/insert", json={"items": list("aabbcc")})
    resp = client.post("/api/v1/topk/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert client.get("/api/v1/topk/query").json()["top"] == []


def test_reset_resizes_k(client):
    resp = client.post("/api/v1/topk/reset", json={"k": 3})
    assert resp.json()["k"] == 3


def test_reset_bad_k_returns_422(client):
    assert client.post("/api/v1/topk/reset", json={"k": 0}).status_code == 422


# ── deterministic Space-Saving over HTTP ─────────────────────────────────────────

def test_deterministic_eviction_over_http(client_det):
    client_det.post("/api/v1/topk/insert", json={"items": ["a", "b", "a", "c"]})
    top = client_det.get("/api/v1/topk/query").json()["top"]
    assert top == [
        {"item": "a", "count": 2, "error": 0},
        {"item": "c", "count": 2, "error": 1},
    ]
    # 'b' was the min-count entry → evicted by 'c'
    assert "b" not in {e["item"] for e in top}


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_insert_query_reset_round_trip(client):
    client.post("/api/v1/topk/insert", json={"items": ["a", "a", "b"]})
    assert client.get("/api/v1/topk/query", params={"n": 1}).json()["top"][0]["item"] == "a"
    client.post("/api/v1/topk/reset", json={})
    assert client.get("/api/v1/topk/stats").json()["total"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–86 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
    assert client.get("/api/v1/reservoir/stats").status_code == 200
    assert client.get("/api/v1/cuckoo/stats").status_code == 200
