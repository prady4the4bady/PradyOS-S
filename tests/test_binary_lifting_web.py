"""Phase 161 — tests for the /api/v1/binarylifting endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.binary_lifting import BinaryLifting
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    # 0 root; 1,2 children of 0; 3,4 children of 1; 5 child of 2
    return TestClient(create_app(binary_lifting=BinaryLifting([-1, 0, 0, 1, 1, 2])))


# ── build ─────────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/binarylifting/build", json={"parents": [-1, 0, 0, 1]}).json()
    assert body["size"] == 4 and body["num_roots"] == 1


def test_build_missing_422(client):
    assert client.post("/api/v1/binarylifting/build", json={}).status_code == 422


def test_build_cycle_422(client):
    resp = client.post("/api/v1/binarylifting/build", json={"parents": [1, 0]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_out_of_range_422(client):
    resp = client.post("/api/v1/binarylifting/build", json={"parents": [9]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── lca ──────────────────────────────────────────────────────────────────────────────────

def test_lca(filled_client):
    assert filled_client.get("/api/v1/binarylifting/lca", params={"u": 3, "v": 4}).json()["lca"] == 1


def test_lca_root(filled_client):
    assert filled_client.get("/api/v1/binarylifting/lca", params={"u": 3, "v": 5}).json()["lca"] == 0


def test_lca_with_ancestor(filled_client):
    assert filled_client.get("/api/v1/binarylifting/lca", params={"u": 3, "v": 1}).json()["lca"] == 1


def test_lca_different_trees_null(client):
    client.post("/api/v1/binarylifting/build", json={"parents": [-1, 0, -1, 2]})
    assert client.get("/api/v1/binarylifting/lca", params={"u": 1, "v": 3}).json()["lca"] is None


# ── kth_ancestor ─────────────────────────────────────────────────────────────────────────

def test_kth_ancestor(filled_client):
    assert filled_client.get("/api/v1/binarylifting/kth_ancestor", params={"v": 3, "k": 1}).json()["ancestor"] == 1
    assert filled_client.get("/api/v1/binarylifting/kth_ancestor", params={"v": 3, "k": 2}).json()["ancestor"] == 0


def test_kth_ancestor_null(filled_client):
    assert filled_client.get("/api/v1/binarylifting/kth_ancestor", params={"v": 3, "k": 3}).json()["ancestor"] is None


# ── depth ────────────────────────────────────────────────────────────────────────────────

def test_depth(filled_client):
    assert filled_client.get("/api/v1/binarylifting/depth", params={"v": 3}).json()["depth"] == 2
    assert filled_client.get("/api/v1/binarylifting/depth", params={"v": 0}).json()["depth"] == 0


def test_depth_out_of_range_422(filled_client):
    resp = filled_client.get("/api/v1/binarylifting/depth", params={"v": 99})
    assert resp.status_code == 422 and "error" in resp.json()


# ── is_ancestor ──────────────────────────────────────────────────────────────────────────

def test_is_ancestor_true(filled_client):
    assert filled_client.get("/api/v1/binarylifting/is_ancestor", params={"u": 0, "v": 3}).json()["is_ancestor"] is True


def test_is_ancestor_false(filled_client):
    assert filled_client.get("/api/v1/binarylifting/is_ancestor", params={"u": 2, "v": 3}).json()["is_ancestor"] is False


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/binarylifting/stats").json()) == {"size", "levels", "max_depth", "num_roots"}


def test_stats_values(filled_client):
    s = filled_client.get("/api/v1/binarylifting/stats").json()
    assert s["size"] == 6 and s["max_depth"] == 2 and s["num_roots"] == 1


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/binarylifting/reset").json()
    assert body["size"] == 0 and body["num_roots"] == 0


# ── round-trip ────────────────────────────────────────────────────────────────────────────

def test_build_then_query(client):
    client.post("/api/v1/binarylifting/build", json={"parents": [-1, 0, 1, 2, 3]})  # chain
    assert client.get("/api/v1/binarylifting/lca", params={"u": 4, "v": 2}).json()["lca"] == 2
    assert client.get("/api/v1/binarylifting/kth_ancestor", params={"v": 4, "k": 4}).json()["ancestor"] == 0
    assert client.get("/api/v1/binarylifting/depth", params={"v": 4}).json()["depth"] == 4


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
                  "rangetree", "leftist", "scapegoat", "binomial"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
