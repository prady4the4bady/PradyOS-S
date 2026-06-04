"""Phase 167 — tests for the /api/v1/convexhull endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.convex_hull import ConvexHull
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    ch = ConvexHull([(0, 0), (0, 10), (10, 10), (10, 0), (5, 5)])
    return TestClient(create_app(convex_hull=ch))


# ── build ─────────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/convexhull/build", json={"points": [[0, 0], [4, 0], [0, 3]]}).json()
    assert body["num_points"] == 3 and body["num_hull_points"] == 3 and body["area"] == 6.0


def test_build_missing_422(client):
    assert client.post("/api/v1/convexhull/build", json={}).status_code == 422


def test_build_bad_point_422(client):
    resp = client.post("/api/v1/convexhull/build", json={"points": [[1, 2], [3]]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_non_num_422(client):
    resp = client.post("/api/v1/convexhull/build", json={"points": [[1, "x"]]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── hull ─────────────────────────────────────────────────────────────────────────────────

def test_hull(filled_client):
    body = filled_client.get("/api/v1/convexhull/hull").json()
    assert body["num_hull_points"] == 4 and {tuple(p) for p in body["hull"]} == {(0, 0), (0, 10), (10, 10), (10, 0)}


def test_hull_empty(client):
    body = client.get("/api/v1/convexhull/hull").json()
    assert body["hull"] == [] and body["num_hull_points"] == 0


# ── contains ─────────────────────────────────────────────────────────────────────────────

def test_contains_interior(filled_client):
    assert filled_client.get("/api/v1/convexhull/contains", params={"x": 5, "y": 5}).json()["contains"] is True


def test_contains_on_edge(filled_client):
    assert filled_client.get("/api/v1/convexhull/contains", params={"x": 0, "y": 5}).json()["contains"] is True


def test_contains_vertex(filled_client):
    assert filled_client.get("/api/v1/convexhull/contains", params={"x": 0, "y": 0}).json()["contains"] is True


def test_contains_outside(filled_client):
    assert filled_client.get("/api/v1/convexhull/contains", params={"x": 11, "y": 5}).json()["contains"] is False


def test_contains_negative_outside(filled_client):
    assert filled_client.get("/api/v1/convexhull/contains", params={"x": -1, "y": 5}).json()["contains"] is False


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/convexhull/stats").json()) == {"num_points", "num_hull_points", "area", "perimeter"}


def test_stats_values(filled_client):
    s = filled_client.get("/api/v1/convexhull/stats").json()
    assert s["num_points"] == 5 and s["num_hull_points"] == 4 and s["area"] == 100.0
    assert abs(s["perimeter"] - 40.0) < 1e-9


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/convexhull/reset").json()
    assert body["num_points"] == 0 and body["num_hull_points"] == 0


# ── round-trip ────────────────────────────────────────────────────────────────────────────

def test_build_then_query(client):
    client.post("/api/v1/convexhull/build", json={"points": [[0, 0], [6, 0], [6, 4], [0, 4], [3, 2]]})
    assert client.get("/api/v1/convexhull/stats").json()["area"] == 24.0
    assert client.get("/api/v1/convexhull/contains", params={"x": 3, "y": 2}).json()["contains"] is True
    assert client.get("/api/v1/convexhull/contains", params={"x": 7, "y": 2}).json()["contains"] is False


def test_collinear_build(client):
    body = client.post("/api/v1/convexhull/build", json={"points": [[0, 0], [1, 1], [2, 2], [3, 3]]}).json()
    assert body["num_hull_points"] == 2 and body["area"] == 0.0


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
                  "implicittreap", "lazysegtree", "tst", "hld", "sparseseg"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
