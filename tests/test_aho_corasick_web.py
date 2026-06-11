"""Phase 142 — tests for the /api/v1/ahocorasick endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.aho_corasick import AhoCorasick
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    ac = AhoCorasick()
    for p in ("he", "she", "his", "hers"):
        ac.add(p)
    return TestClient(create_app(aho_corasick=ac))


# ── add ──────────────────────────────────────────────────────────────────────────────────

def test_add_returns_num(client):
    body = client.post("/api/v1/ahocorasick/add", json={"pattern": "he"}).json()
    assert body["added"] is True and body["num_patterns"] == 1


def test_add_dup(client):
    client.post("/api/v1/ahocorasick/add", json={"pattern": "he"})
    body = client.post("/api/v1/ahocorasick/add", json={"pattern": "he"}).json()
    assert body["added"] is False and body["num_patterns"] == 1


def test_add_missing_pattern_422(client):
    assert client.post("/api/v1/ahocorasick/add", json={}).status_code == 422


def test_add_empty_422(client):
    resp = client.post("/api/v1/ahocorasick/add", json={"pattern": ""})
    assert resp.status_code == 422 and "error" in resp.json()


def test_add_non_str_422(client):
    resp = client.post("/api/v1/ahocorasick/add", json={"pattern": 5})
    assert resp.status_code == 422 and "error" in resp.json()


def test_add_many(client):
    body = client.post("/api/v1/ahocorasick/add_many",
                       json={"patterns": ["a", "b", "a", "c"]}).json()
    assert body["added"] == 3 and body["num_patterns"] == 3


def test_add_many_missing_422(client):
    assert client.post("/api/v1/ahocorasick/add_many", json={}).status_code == 422


# ── search ─────────────────────────────────────────────────────────────────────────────────

def test_search(built_client):
    body = built_client.post("/api/v1/ahocorasick/search", json={"text": "ushers"}).json()
    assert body["matches"] == [["he", 3], ["she", 3], ["hers", 5]] and body["count"] == 3


def test_search_no_match(built_client):
    body = built_client.post("/api/v1/ahocorasick/search", json={"text": "xyz"}).json()
    assert body["matches"] == [] and body["count"] == 0


def test_search_empty_text(built_client):
    body = built_client.post("/api/v1/ahocorasick/search", json={"text": ""}).json()
    assert body["matches"] == []


def test_search_missing_text_422(built_client):
    assert built_client.post("/api/v1/ahocorasick/search", json={}).status_code == 422


def test_search_non_str_text_422(built_client):
    resp = built_client.post("/api/v1/ahocorasick/search", json={"text": 123})
    assert resp.status_code == 422 and "error" in resp.json()


def test_overlapping(client):
    client.post("/api/v1/ahocorasick/add", json={"pattern": "aa"})
    body = client.post("/api/v1/ahocorasick/search", json={"text": "aaaa"}).json()
    assert body["count"] == 3 and body["matches"] == [["aa", 1], ["aa", 2], ["aa", 3]]


def test_build_then_search(client):
    client.post("/api/v1/ahocorasick/add_many", json={"patterns": ["cat", "dog"]})
    body = client.post("/api/v1/ahocorasick/search", json={"text": "dogcat"}).json()
    assert body["matches"] == [["dog", 2], ["cat", 5]]


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/ahocorasick/stats").json()) == {
        "num_patterns", "num_nodes", "built"}


def test_stats_defaults(client):
    s = client.get("/api/v1/ahocorasick/stats").json()
    assert s["num_patterns"] == 0


def test_stats_after_add(built_client):
    s = built_client.get("/api/v1/ahocorasick/stats").json()
    assert s["num_patterns"] == 4


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    body = built_client.request("DELETE", "/api/v1/ahocorasick/reset").json()
    assert body["num_patterns"] == 0


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/ahocorasick/reset").status_code == 200


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
                  "suffixarray"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
