"""Phase 157 — tests for the /api/v1/rangetree endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.range_tree import RangeTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    rt = RangeTree([(10, 10), (50, 50), (90, 90), (30, 70), (70, 30)])
    return TestClient(create_app(range_tree=rt))


# ── build ─────────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/rangetree/build", json={"points": [[1, 1], [2, 2], [3, 3]]}).json()
    assert body["size"] == 3 and body["x_min"] == 1 and body["x_max"] == 3


def test_build_missing_422(client):
    assert client.post("/api/v1/rangetree/build", json={}).status_code == 422


def test_build_bad_point_422(client):
    resp = client.post("/api/v1/rangetree/build", json={"points": [[1, 2], [3]]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_non_num_422(client):
    resp = client.post("/api/v1/rangetree/build", json={"points": [[1, "x"]]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── range_query ──────────────────────────────────────────────────────────────────────────

def test_range_query(filled_client):
    body = filled_client.get("/api/v1/rangetree/range_query",
                             params={"x_min": 0, "y_min": 0, "x_max": 60, "y_max": 60}).json()
    assert body["points"] == [[10, 10], [50, 50]] and body["count"] == 2


def test_range_query_full(filled_client):
    body = filled_client.get("/api/v1/rangetree/range_query",
                             params={"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100}).json()
    assert body["count"] == 5


def test_range_query_empty_match(filled_client):
    body = filled_client.get("/api/v1/rangetree/range_query",
                             params={"x_min": 0, "y_min": 0, "x_max": 5, "y_max": 5}).json()
    assert body["points"] == [] and body["count"] == 0


def test_range_query_inverted_422(filled_client):
    resp = filled_client.get("/api/v1/rangetree/range_query",
                             params={"x_min": 60, "y_min": 60, "x_max": 10, "y_max": 10})
    assert resp.status_code == 422 and "error" in resp.json()


# ── range_count ──────────────────────────────────────────────────────────────────────────

def test_range_count(filled_client):
    body = filled_client.get("/api/v1/rangetree/range_count",
                             params={"x_min": 0, "y_min": 0, "x_max": 60, "y_max": 60}).json()
    assert body["count"] == 2


def test_range_count_full(filled_client):
    body = filled_client.get("/api/v1/rangetree/range_count",
                             params={"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100}).json()
    assert body["count"] == 5


def test_range_count_inverted_422(filled_client):
    resp = filled_client.get("/api/v1/rangetree/range_count",
                             params={"x_min": 0, "y_min": 60, "x_max": 100, "y_max": 10})
    assert resp.status_code == 422 and "error" in resp.json()


def test_count_matches_query(filled_client):
    q = filled_client.get("/api/v1/rangetree/range_query",
                          params={"x_min": 20, "y_min": 20, "x_max": 80, "y_max": 80}).json()
    c = filled_client.get("/api/v1/rangetree/range_count",
                          params={"x_min": 20, "y_min": 20, "x_max": 80, "y_max": 80}).json()
    assert q["count"] == c["count"]


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/rangetree/stats").json()) == {"size", "height", "x_min", "x_max"}


def test_stats_values(filled_client):
    s = filled_client.get("/api/v1/rangetree/stats").json()
    assert s["size"] == 5 and s["x_min"] == 10 and s["x_max"] == 90


def test_stats_empty(client):
    s = client.get("/api/v1/rangetree/stats").json()
    assert s["size"] == 0 and s["x_min"] is None


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/rangetree/reset").json()
    assert body["size"] == 0 and body["x_min"] is None


# ── round-trip ────────────────────────────────────────────────────────────────────────────

def test_build_then_query(client):
    client.post("/api/v1/rangetree/build", json={"points": [[1, 1], [2, 2], [3, 3]]})
    assert client.get("/api/v1/rangetree/range_count",
                      params={"x_min": 0, "y_min": 0, "x_max": 2, "y_max": 2}).json()["count"] == 2
    assert client.get("/api/v1/rangetree/range_query",
                      params={"x_min": 0, "y_min": 0, "x_max": 5, "y_max": 5}).json()["count"] == 3


# ── regression ────────────────────────────────────────────────────────────────────────────

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
                  "suffixarray", "ahocorasick", "xortrie", "minmaxheap", "cartesiantree",
                  "fenwick2d", "sqrtdecomp", "lichao", "perseg", "pairingheap",
                  "suffixautomaton", "veb", "prquadtree", "fibonacci", "avl", "btree"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
