"""Phase 163 — tests for the /api/v1/lazysegtree endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.lazy_segment_tree import LazySegmentTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    return TestClient(create_app(lazy_segment_tree=LazySegmentTree([1, 2, 3, 4, 5])))


# ── range_add / range_assign ──────────────────────────────────────────────────────────────

def test_range_add_returns_total(filled_client):
    body = filled_client.post("/api/v1/lazysegtree/range_add", json={"lo": 0, "hi": 4, "delta": 10}).json()
    assert body["total"] == 15 + 50


def test_range_add_missing_422(client):
    assert client.post("/api/v1/lazysegtree/range_add", json={"lo": 0, "hi": 1}).status_code == 422


def test_range_add_lo_gt_hi_422(filled_client):
    resp = filled_client.post("/api/v1/lazysegtree/range_add", json={"lo": 4, "hi": 1, "delta": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_range_add_non_num_422(filled_client):
    resp = filled_client.post("/api/v1/lazysegtree/range_add", json={"lo": 0, "hi": 0, "delta": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


def test_range_assign(filled_client):
    filled_client.post("/api/v1/lazysegtree/range_assign", json={"lo": 1, "hi": 3, "value": 0})
    assert filled_client.get("/api/v1/lazysegtree/range_sum", params={"lo": 0, "hi": 4}).json()["sum"] == 6


# ── queries ──────────────────────────────────────────────────────────────────────────────

def test_range_sum(filled_client):
    assert filled_client.get("/api/v1/lazysegtree/range_sum", params={"lo": 0, "hi": 4}).json()["sum"] == 15


def test_range_min(filled_client):
    assert filled_client.get("/api/v1/lazysegtree/range_min", params={"lo": 0, "hi": 4}).json()["min"] == 1


def test_range_max(filled_client):
    assert filled_client.get("/api/v1/lazysegtree/range_max", params={"lo": 0, "hi": 4}).json()["max"] == 5


def test_range_sum_out_of_range_422(filled_client):
    resp = filled_client.get("/api/v1/lazysegtree/range_sum", params={"lo": 0, "hi": 99})
    assert resp.status_code == 422 and "error" in resp.json()


def test_point_query(filled_client):
    assert filled_client.get("/api/v1/lazysegtree/point_query", params={"i": 2}).json()["value"] == 3


# ── build / stats / reset ─────────────────────────────────────────────────────────────────

def test_build(client):
    body = client.post("/api/v1/lazysegtree/build", json={"values": [10, 20, 30]}).json()
    assert body["size"] == 3 and body["total"] == 60


def test_build_non_num_422(client):
    resp = client.post("/api/v1/lazysegtree/build", json={"values": [1, "x"]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_stats_keys(client):
    assert set(client.get("/api/v1/lazysegtree/stats").json()) == {"size", "total", "min", "max"}


def test_stats_defaults(client):
    s = client.get("/api/v1/lazysegtree/stats").json()
    assert s["size"] == 16 and s["total"] == 0


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/lazysegtree/reset", json={}).json()
    assert body["size"] == 0


def test_reset_with_values(client):
    body = client.request("DELETE", "/api/v1/lazysegtree/reset", json={"values": [1, 2, 3]}).json()
    assert body["size"] == 3 and body["total"] == 6


# ── workflow (assign clears pending add, then add accumulates) ─────────────────────────────

def test_assign_then_add_workflow(client):
    client.post("/api/v1/lazysegtree/build", json={"values": [0, 0, 0, 0]})
    client.post("/api/v1/lazysegtree/range_add", json={"lo": 0, "hi": 3, "delta": 5})
    client.post("/api/v1/lazysegtree/range_assign", json={"lo": 1, "hi": 2, "value": 100})
    client.post("/api/v1/lazysegtree/range_add", json={"lo": 0, "hi": 3, "delta": 1})
    assert client.get("/api/v1/lazysegtree/range_sum", params={"lo": 0, "hi": 3}).json()["sum"] == 6 + 101 + 101 + 6
    assert client.get("/api/v1/lazysegtree/point_query", params={"i": 1}).json()["value"] == 101


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
                  "suffixautomaton", "veb", "prquadtree", "fibonacci", "avl", "btree",
                  "rangetree", "leftist", "scapegoat", "binomial", "binarylifting",
                  "implicittreap"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
