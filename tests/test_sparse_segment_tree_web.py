"""Phase 166 — tests for the /api/v1/sparseseg endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.sparse_segment_tree import SparseSegmentTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    sst = SparseSegmentTree(10 ** 9)
    for i, v in [(5, 10), (1000000, 20), (999999998, 30)]:
        sst.update(i, v)
    return TestClient(create_app(sparse_segment_tree=sst))


# ── update ────────────────────────────────────────────────────────────────────────────────

def test_update_returns_total(client):
    body = client.post("/api/v1/sparseseg/update", json={"index": 5, "delta": 10}).json()
    assert body["total"] == 10


def test_update_missing_422(client):
    assert client.post("/api/v1/sparseseg/update", json={"index": 5}).status_code == 422


def test_update_out_of_range_422(client):
    resp = client.post("/api/v1/sparseseg/update", json={"index": 2 ** 63, "delta": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_update_non_num_422(client):
    resp = client.post("/api/v1/sparseseg/update", json={"index": 0, "delta": "x"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── range_sum ────────────────────────────────────────────────────────────────────────────

def test_range_sum(filled_client):
    assert filled_client.get("/api/v1/sparseseg/range_sum", params={"lo": 0, "hi": 10 ** 9 - 1}).json()["sum"] == 60


def test_range_sum_partial(filled_client):
    assert filled_client.get("/api/v1/sparseseg/range_sum", params={"lo": 0, "hi": 1000000}).json()["sum"] == 30


def test_range_sum_out_of_range_422(filled_client):
    resp = filled_client.get("/api/v1/sparseseg/range_sum", params={"lo": 0, "hi": 10 ** 12})
    assert resp.status_code == 422 and "error" in resp.json()


def test_range_sum_inverted_422(filled_client):
    resp = filled_client.get("/api/v1/sparseseg/range_sum", params={"lo": 100, "hi": 5})
    assert resp.status_code == 422 and "error" in resp.json()


# ── point_query / point_assign ───────────────────────────────────────────────────────────

def test_point_query(filled_client):
    assert filled_client.get("/api/v1/sparseseg/point_query", params={"index": 5}).json()["value"] == 10


def test_point_query_zero(filled_client):
    assert filled_client.get("/api/v1/sparseseg/point_query", params={"index": 50}).json()["value"] == 0


def test_point_assign(filled_client):
    body = filled_client.post("/api/v1/sparseseg/point_assign", json={"index": 5, "value": 100}).json()
    assert body["total"] == 150                          # 60 - 10 + 100
    assert filled_client.get("/api/v1/sparseseg/point_query", params={"index": 5}).json()["value"] == 100


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/sparseseg/stats").json()) == {"universe", "num_nodes", "total"}


def test_stats_defaults(client):
    s = client.get("/api/v1/sparseseg/stats").json()
    assert s["universe"] == 2 ** 62 and s["total"] == 0 and s["num_nodes"] == 0


def test_stats_values(filled_client):
    s = filled_client.get("/api/v1/sparseseg/stats").json()
    assert s["universe"] == 10 ** 9 and s["total"] == 60 and s["num_nodes"] > 0


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/sparseseg/reset").json()
    assert body["num_nodes"] == 0 and body["total"] == 0


# ── workflow ──────────────────────────────────────────────────────────────────────────────

def test_workflow(client):
    for i, v in [(0, 1), (5 * 10 ** 17, 2), (10 ** 18 - 1, 3)]:
        client.post("/api/v1/sparseseg/update", json={"index": i, "delta": v})
    assert client.get("/api/v1/sparseseg/range_sum", params={"lo": 0, "hi": 10 ** 18 - 1}).json()["sum"] == 6
    assert client.get("/api/v1/sparseseg/range_sum", params={"lo": 0, "hi": 10 ** 17}).json()["sum"] == 1
    assert client.get("/api/v1/sparseseg/point_query", params={"index": 5 * 10 ** 17}).json()["value"] == 2


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
                  "implicittreap", "lazysegtree", "tst", "hld"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
