"""Phase 145 — tests for the /api/v1/cartesiantree endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.cartesian_tree import CartesianTree
from pradyos.sovereign_web import create_app


VALS = [5, 3, 8, 1, 9, 2]   # global min 1 at index 3


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    return TestClient(create_app(cartesian_tree=CartesianTree(VALS)))


# ── build ──────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/cartesiantree/build", json={"values": VALS}).json()
    assert body["size"] == 6 and body["root_index"] == 3


def test_build_missing_values_422(client):
    assert client.post("/api/v1/cartesiantree/build", json={}).status_code == 422


def test_build_non_numeric_422(client):
    resp = client.post("/api/v1/cartesiantree/build", json={"values": [1, "x"]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── range_min ────────────────────────────────────────────────────────────────────────────

def test_range_min(built_client):
    body = built_client.get("/api/v1/cartesiantree/range_min", params={"lo": 0, "hi": 2}).json()
    assert body["min"] == 3 and body["argmin"] == 1


def test_range_min_full(built_client):
    body = built_client.get("/api/v1/cartesiantree/range_min", params={"lo": 0, "hi": 5}).json()
    assert body["min"] == 1 and body["argmin"] == 3


def test_range_min_subrange(built_client):
    body = built_client.get("/api/v1/cartesiantree/range_min", params={"lo": 4, "hi": 5}).json()
    assert body["min"] == 2 and body["argmin"] == 5


def test_range_min_missing_param_422(built_client):
    assert built_client.get("/api/v1/cartesiantree/range_min", params={"lo": 0}).status_code == 422


def test_range_min_lo_gt_hi_422(built_client):
    resp = built_client.get("/api/v1/cartesiantree/range_min", params={"lo": 3, "hi": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_range_min_out_of_range_422(built_client):
    resp = built_client.get("/api/v1/cartesiantree/range_min", params={"lo": 0, "hi": 99})
    assert resp.status_code == 422 and "error" in resp.json()


# ── structure ──────────────────────────────────────────────────────────────────────────────

def test_structure(built_client):
    s = built_client.get("/api/v1/cartesiantree/structure").json()
    assert set(s) == {"root", "parent", "left", "right"} and s["root"] == 3
    assert len(s["parent"]) == 6


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/cartesiantree/stats").json()) == {"size", "height", "root_index"}


def test_stats_defaults(client):
    s = client.get("/api/v1/cartesiantree/stats").json()
    assert s["size"] == 0 and s["root_index"] == -1


def test_stats_after_build(built_client):
    assert built_client.get("/api/v1/cartesiantree/stats").json()["size"] == 6


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    body = built_client.request("DELETE", "/api/v1/cartesiantree/reset").json()
    assert body["size"] == 0 and body["root_index"] == -1


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/cartesiantree/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_build_then_range_min(client):
    client.post("/api/v1/cartesiantree/build", json={"values": [4, 2, 6, 1, 5]})
    body = client.get("/api/v1/cartesiantree/range_min", params={"lo": 0, "hi": 2}).json()
    assert body["min"] == 2


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
                  "suffixarray", "ahocorasick", "xortrie", "minmaxheap"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
