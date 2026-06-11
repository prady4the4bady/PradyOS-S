"""Phase 165 — tests for the /api/v1/hld endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.heavy_light import HeavyLight
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    # 0 root; 1,2 children of 0; 3,4 children of 1; 5 child of 2
    hl = HeavyLight([-1, 0, 0, 1, 1, 2], [10, 20, 30, 40, 50, 60])
    return TestClient(create_app(heavy_light=hl))


# ── build ─────────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/hld/build", json={"parents": [-1, 0, 0], "values": [1, 2, 3]}).json()
    assert body["size"] == 3 and body["total"] == 6


def test_build_missing_422(client):
    assert client.post("/api/v1/hld/build", json={}).status_code == 422


def test_build_two_roots_422(client):
    resp = client.post("/api/v1/hld/build", json={"parents": [-1, -1]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_values_mismatch_422(client):
    resp = client.post("/api/v1/hld/build", json={"parents": [-1, 0], "values": [1, 2, 3]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── update ────────────────────────────────────────────────────────────────────────────────

def test_update(filled_client):
    body = filled_client.post("/api/v1/hld/update", json={"node": 0, "value": 100}).json()
    assert body["total"] == 300                          # 210 - 10 + 100


def test_update_missing_422(client):
    assert client.post("/api/v1/hld/update", json={"node": 0}).status_code == 422


# ── path queries ───────────────────────────────────────────────────────────────────────────

def test_path_sum(filled_client):
    assert filled_client.get("/api/v1/hld/path_sum", params={"u": 3, "v": 4}).json()["sum"] == 110


def test_path_max(filled_client):
    assert filled_client.get("/api/v1/hld/path_max", params={"u": 3, "v": 4}).json()["max"] == 50


def test_path_through_root(filled_client):
    assert filled_client.get("/api/v1/hld/path_sum", params={"u": 3, "v": 5}).json()["sum"] == 160


def test_path_node_out_of_range_422(filled_client):
    resp = filled_client.get("/api/v1/hld/path_sum", params={"u": 0, "v": 99})
    assert resp.status_code == 422 and "error" in resp.json()


# ── subtree / depth ──────────────────────────────────────────────────────────────────────

def test_subtree_sum(filled_client):
    assert filled_client.get("/api/v1/hld/subtree_sum", params={"v": 1}).json()["sum"] == 110
    assert filled_client.get("/api/v1/hld/subtree_sum", params={"v": 0}).json()["sum"] == 210


def test_depth(filled_client):
    assert filled_client.get("/api/v1/hld/depth", params={"v": 3}).json()["depth"] == 2
    assert filled_client.get("/api/v1/hld/depth", params={"v": 0}).json()["depth"] == 0


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/hld/stats").json()) == {"size", "total", "max", "num_chains"}


def test_stats_values(filled_client):
    s = filled_client.get("/api/v1/hld/stats").json()
    assert s["size"] == 6 and s["total"] == 210 and s["max"] == 60


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/hld/reset").json()
    assert body["size"] == 0


# ── round-trip ────────────────────────────────────────────────────────────────────────────

def test_build_then_query(client):
    client.post("/api/v1/hld/build", json={"parents": [-1, 0, 1, 2], "values": [1, 2, 3, 4]})  # chain
    assert client.get("/api/v1/hld/path_sum", params={"u": 0, "v": 3}).json()["sum"] == 10
    client.post("/api/v1/hld/update", json={"node": 2, "value": 100})
    assert client.get("/api/v1/hld/path_sum", params={"u": 0, "v": 3}).json()["sum"] == 107
    assert client.get("/api/v1/hld/path_max", params={"u": 0, "v": 3}).json()["max"] == 100


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
                  "implicittreap", "lazysegtree", "tst"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
