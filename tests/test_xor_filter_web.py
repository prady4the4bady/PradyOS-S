"""Phase 100 — tests for the /api/v1/xorfilter endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.xor_filter import XorFilter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app XorFilter (8-bit, unbuilt) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    # A pre-built 16-bit filter injected → membership is exact, non-members ~certainly absent.
    xf = XorFilter(bits_per_entry=16, seed=0)
    xf.build([f"member-{i}" for i in range(2000)])
    return TestClient(create_app(xor_filter=xf))


# ── build ────────────────────────────────────────────────────────────────────────

def test_build_returns_built(client):
    resp = client.post("/api/v1/xorfilter/build", json={"keys": ["a", "b", "c"]})
    assert resp.status_code == 200
    assert resp.json()["built"] is True and resp.json()["n"] == 3


def test_build_missing_keys_returns_422(client):
    assert client.post("/api/v1/xorfilter/build", json={}).status_code == 422


def test_build_non_dict_body_returns_422(client):
    assert client.post("/api/v1/xorfilter/build", json=["a", "b"]).status_code == 422


def test_build_non_list_keys_returns_422(client):
    assert client.post("/api/v1/xorfilter/build", json={"keys": "nope"}).status_code == 422


def test_build_dedups(client):
    resp = client.post("/api/v1/xorfilter/build", json={"keys": ["a", "a", "b"]})
    assert resp.json()["n"] == 2


# ── contains ────────────────────────────────────────────────────────────────────

def test_contains_member_true(client):
    client.post("/api/v1/xorfilter/build", json={"keys": [f"k{i}" for i in range(500)]})
    body = client.get("/api/v1/xorfilter/contains", params={"key": "k200"}).json()
    assert body["key"] == "k200" and body["contained"] is True


def test_membership_no_false_negatives(client):
    keys = [f"k{i}" for i in range(500)]
    client.post("/api/v1/xorfilter/build", json={"keys": keys})
    assert all(
        client.get("/api/v1/xorfilter/contains", params={"key": k}).json()["contained"]
        for k in keys[:50]
    )


def test_contains_non_member_false(built_client):
    body = built_client.get("/api/v1/xorfilter/contains", params={"key": "not-a-member-xyz"}).json()
    assert body["contained"] is False        # 16-bit FPR ≈ 1/65536


def test_contains_before_build_returns_422(client):
    resp = client.get("/api/v1/xorfilter/contains", params={"key": "x"})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_contains_missing_key_returns_422(client):
    client.post("/api/v1/xorfilter/build", json={"keys": ["a"]})
    assert client.get("/api/v1/xorfilter/contains").status_code == 422


def test_contains_after_reset_returns_422(client):
    client.post("/api/v1/xorfilter/build", json={"keys": ["a", "b"]})
    client.post("/api/v1/xorfilter/reset", json={})
    assert client.get("/api/v1/xorfilter/contains", params={"key": "a"}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/xorfilter/stats").json()
    assert set(data) == {"bits_per_entry", "built", "n", "array_size",
                         "segment_size", "false_positive_rate"}


def test_stats_unbuilt(client):
    data = client.get("/api/v1/xorfilter/stats").json()
    assert data["built"] is False and data["n"] == 0


def test_stats_after_build(client):
    client.post("/api/v1/xorfilter/build", json={"keys": [f"k{i}" for i in range(300)]})
    data = client.get("/api/v1/xorfilter/stats").json()
    assert data["built"] is True and data["n"] == 300 and data["array_size"] > 300


def test_stats_default_bits(client):
    assert client.get("/api/v1/xorfilter/stats").json()["bits_per_entry"] == 8


# ── rebuild / reset ──────────────────────────────────────────────────────────────

def test_rebuild_replaces(client):
    client.post("/api/v1/xorfilter/build", json={"keys": [f"A{i}" for i in range(300)]})
    client.post("/api/v1/xorfilter/build", json={"keys": [f"B{i}" for i in range(300)]})
    assert client.get("/api/v1/xorfilter/contains", params={"key": "B100"}).json()["contained"] is True


def test_reset_clears(client):
    client.post("/api/v1/xorfilter/build", json={"keys": ["a", "b"]})
    resp = client.post("/api/v1/xorfilter/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["built"] is False and resp.json()["n"] == 0


def test_reset_reconfigures_bits(client):
    resp = client.post("/api/v1/xorfilter/reset", json={"bits_per_entry": 16})
    assert resp.json()["bits_per_entry"] == 16


def test_reset_bad_bits_returns_422(client):
    assert client.post("/api/v1/xorfilter/reset", json={"bits_per_entry": 0}).status_code == 422


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–99 routes still respond
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
    assert client.get("/api/v1/sample/stats").status_code == 200
    assert client.get("/api/v1/misragries/stats").status_code == 200
