"""Phase 143 — tests for the /api/v1/xortrie endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.xor_trie import XorTrie
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    t = XorTrie(width=8)
    for v in (2, 20, 12):
        t.insert(v)
    return TestClient(create_app(xor_trie=t))


# ── insert ─────────────────────────────────────────────────────────────────────────────

def test_insert_returns_size(client):
    body = client.post("/api/v1/xortrie/insert", json={"value": 5}).json()
    assert body["size"] == 1


def test_insert_missing_value_422(client):
    assert client.post("/api/v1/xortrie/insert", json={}).status_code == 422


def test_insert_out_of_range_422(client):
    # default width 32 → value must be < 2^32
    resp = client.post("/api/v1/xortrie/insert", json={"value": 2 ** 32})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_negative_422(client):
    assert client.post("/api/v1/xortrie/insert", json={"value": -1}).status_code == 422


def test_insert_bool_422(client):
    resp = client.post("/api/v1/xortrie/insert", json={"value": True})
    assert resp.status_code == 422 and "error" in resp.json()


# ── query (max/min xor) ────────────────────────────────────────────────────────────────────

def test_query(built_client):
    body = built_client.post("/api/v1/xortrie/query", json={"query": 0}).json()
    assert body["max_xor"] == 20 and body["min_xor"] == 2   # 0^x over {2,20,12}


def test_query_specific(built_client):
    body = built_client.post("/api/v1/xortrie/query", json={"query": 31}).json()
    assert body["max_xor"] == max(31 ^ x for x in (2, 20, 12))


def test_query_empty_422(client):
    resp = client.post("/api/v1/xortrie/query", json={"query": 5})
    assert resp.status_code == 422 and "error" in resp.json()


def test_query_missing_422(built_client):
    assert built_client.post("/api/v1/xortrie/query", json={}).status_code == 422


# ── remove ───────────────────────────────────────────────────────────────────────────────

def test_remove_present(built_client):
    body = built_client.request("DELETE", "/api/v1/xortrie/remove", json={"value": 20}).json()
    assert body["removed"] is True and body["size"] == 2


def test_remove_absent(built_client):
    body = built_client.request("DELETE", "/api/v1/xortrie/remove", json={"value": 99}).json()
    assert body["removed"] is False


def test_remove_missing_422(client):
    assert client.request("DELETE", "/api/v1/xortrie/remove", json={}).status_code == 422


# ── count_xor_less ─────────────────────────────────────────────────────────────────────────

def test_count_xor_less(built_client):
    # query 0 → count x with x < 13 over {2,20,12} = {2,12} = 2
    body = built_client.post("/api/v1/xortrie/count_xor_less", json={"query": 0, "k": 13}).json()
    assert body["count"] == 2


def test_count_missing_422(built_client):
    assert built_client.post("/api/v1/xortrie/count_xor_less", json={"query": 0}).status_code == 422


def test_count_non_int_k_422(built_client):
    resp = built_client.post("/api/v1/xortrie/count_xor_less", json={"query": 0, "k": 1.5})
    assert resp.status_code == 422 and "error" in resp.json()


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/xortrie/stats").json()) == {"size", "width", "num_nodes"}


def test_stats_defaults(client):
    s = client.get("/api/v1/xortrie/stats").json()
    assert s["size"] == 0 and s["width"] == 32


def test_stats_after_insert(built_client):
    assert built_client.get("/api/v1/xortrie/stats").json()["size"] == 3


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    body = built_client.request("DELETE", "/api/v1/xortrie/reset").json()
    assert body["size"] == 0


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/xortrie/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_insert_then_query(client):
    for v in (100, 200, 300):
        client.post("/api/v1/xortrie/insert", json={"value": v})
    body = client.post("/api/v1/xortrie/query", json={"query": 150}).json()
    assert body["max_xor"] == max(150 ^ x for x in (100, 200, 300))


# ── regression ────────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier", "minhashlsh", "tinylfu", "hyperminhash", "scalablebloom",
                  "rendezvous", "maglev", "iblt", "bbitminhash", "cusketch", "jump",
                  "frugal", "simhashlsh", "randomprojection", "gcs", "fmsketch", "ams",
                  "prioritysample", "cuckoohash", "splaytree", "rankselect", "wavelet",
                  "skewheap", "intervaltree", "sparsetable", "kdtree", "radixtree",
                  "suffixarray", "ahocorasick"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
