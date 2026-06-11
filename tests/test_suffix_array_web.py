"""Phase 141 — tests for the /api/v1/suffixarray endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.suffix_array import SuffixArray
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    return TestClient(create_app(suffix_array=SuffixArray("banana")))


# ── build ──────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/suffixarray/build", json={"text": "banana"}).json()
    assert body["size"] == 6 and body["num_suffixes"] == 6


def test_build_missing_text_422(client):
    assert client.post("/api/v1/suffixarray/build", json={}).status_code == 422


def test_build_non_str_422(client):
    resp = client.post("/api/v1/suffixarray/build", json={"text": 123})
    assert resp.status_code == 422 and "error" in resp.json()


# ── search ─────────────────────────────────────────────────────────────────────────────

def test_search_found(built_client):
    body = built_client.post("/api/v1/suffixarray/search", json={"pattern": "ana"}).json()
    assert body["contains"] is True and body["count"] == 2 and body["positions"] == [1, 3]


def test_search_single_char(built_client):
    body = built_client.post("/api/v1/suffixarray/search", json={"pattern": "a"}).json()
    assert body["count"] == 3 and body["positions"] == [1, 3, 5]


def test_search_absent(built_client):
    body = built_client.post("/api/v1/suffixarray/search", json={"pattern": "xyz"}).json()
    assert body["contains"] is False and body["count"] == 0 and body["positions"] == []


def test_search_full_text(built_client):
    body = built_client.post("/api/v1/suffixarray/search", json={"pattern": "banana"}).json()
    assert body["contains"] is True and body["positions"] == [0]


def test_search_pattern_longer_than_text(built_client):
    body = built_client.post("/api/v1/suffixarray/search", json={"pattern": "bananana"}).json()
    assert body["contains"] is False


def test_search_empty_pattern_422(built_client):
    resp = built_client.post("/api/v1/suffixarray/search", json={"pattern": ""})
    assert resp.status_code == 422 and "error" in resp.json()


def test_search_missing_pattern_422(client):
    assert client.post("/api/v1/suffixarray/search", json={}).status_code == 422


def test_build_then_search(client):
    client.post("/api/v1/suffixarray/build", json={"text": "mississippi"})
    body = client.post("/api/v1/suffixarray/search", json={"pattern": "issi"}).json()
    assert body["positions"] == [1, 4]


def test_overlapping(client):
    client.post("/api/v1/suffixarray/build", json={"text": "aaaa"})
    body = client.post("/api/v1/suffixarray/search", json={"pattern": "aa"}).json()
    assert body["count"] == 3 and body["positions"] == [0, 1, 2]


# ── array ──────────────────────────────────────────────────────────────────────────────

def test_array(built_client):
    body = built_client.get("/api/v1/suffixarray/array").json()
    assert body["suffix_array"] == [5, 3, 1, 0, 4, 2] and len(body["lcp_array"]) == 6


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/suffixarray/stats").json()) == {
        "size", "num_suffixes", "distinct_substrings"}


def test_stats_defaults(client):
    s = client.get("/api/v1/suffixarray/stats").json()
    assert s["size"] == 0 and s["distinct_substrings"] == 0


def test_stats_after_build(built_client):
    s = built_client.get("/api/v1/suffixarray/stats").json()
    assert s["size"] == 6 and s["distinct_substrings"] == 15


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    body = built_client.request("DELETE", "/api/v1/suffixarray/reset").json()
    assert body["size"] == 0


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/suffixarray/reset").status_code == 200


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
                  "skewheap", "intervaltree", "sparsetable", "kdtree", "radixtree"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
