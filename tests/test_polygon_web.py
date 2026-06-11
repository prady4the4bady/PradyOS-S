"""Phase 168 — tests for the /api/v1/polygon endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.polygon import Polygon
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    poly = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])     # CCW square
    return TestClient(create_app(polygon=poly))


# ── build ─────────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/polygon/build", json={"vertices": [[0, 0], [6, 0], [0, 3]]}).json()
    assert body["num_vertices"] == 3 and body["area"] == 9.0 and body["is_convex"] is True


def test_build_missing_422(client):
    assert client.post("/api/v1/polygon/build", json={}).status_code == 422


def test_build_bad_vertex_422(client):
    resp = client.post("/api/v1/polygon/build", json={"vertices": [[0, 0], [1]]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_non_num_422(client):
    resp = client.post("/api/v1/polygon/build", json={"vertices": [[0, 0], [1, "y"]]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_nonconvex(client):
    body = client.post("/api/v1/polygon/build",
                       json={"vertices": [[0, 0], [4, 0], [4, 2], [2, 2], [2, 4], [0, 4]]}).json()
    assert body["is_convex"] is False and body["area"] == 12.0


# ── stats ─────────────────────────────────────────────────────────────────────────────────

def test_stats_square(filled_client):
    s = filled_client.get("/api/v1/polygon/stats").json()
    assert s["num_vertices"] == 4 and s["area"] == 16.0 and s["is_convex"] is True
    assert s["orientation"] == "CCW" and abs(s["perimeter"] - 16.0) < 1e-9


def test_stats_keys(client):
    assert set(client.get("/api/v1/polygon/stats").json()) == {
        "num_vertices", "area", "perimeter", "is_convex", "orientation"}


def test_stats_empty(client):
    s = client.get("/api/v1/polygon/stats").json()
    assert s["num_vertices"] == 0 and s["area"] == 0.0 and s["orientation"] == "degenerate"


# ── contains ─────────────────────────────────────────────────────────────────────────────

def test_contains_interior(filled_client):
    assert filled_client.get("/api/v1/polygon/contains", params={"x": 2, "y": 2}).json()["contains"] is True


def test_contains_edge(filled_client):
    assert filled_client.get("/api/v1/polygon/contains", params={"x": 0, "y": 2}).json()["contains"] is True


def test_contains_vertex(filled_client):
    assert filled_client.get("/api/v1/polygon/contains", params={"x": 0, "y": 0}).json()["contains"] is True


def test_contains_outside(filled_client):
    assert filled_client.get("/api/v1/polygon/contains", params={"x": 5, "y": 2}).json()["contains"] is False


# ── centroid / reset / orientation ────────────────────────────────────────────────────────

def test_centroid_square(filled_client):
    c = filled_client.get("/api/v1/polygon/centroid").json()["centroid"]
    assert abs(c[0] - 2) < 1e-9 and abs(c[1] - 2) < 1e-9


def test_centroid_empty_null(client):
    assert client.get("/api/v1/polygon/centroid").json()["centroid"] is None


def test_orientation_cw(client):
    body = client.post("/api/v1/polygon/build",
                       json={"vertices": [[0, 0], [0, 4], [4, 4], [4, 0]]}).json()
    assert body["orientation"] == "CW" and body["area"] == 16.0


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/polygon/reset").json()
    assert body["num_vertices"] == 0 and body["area"] == 0.0


# ── round-trip ────────────────────────────────────────────────────────────────────────────

def test_build_then_query_nonconvex(client):
    client.post("/api/v1/polygon/build",
                json={"vertices": [[0, 0], [4, 0], [4, 2], [2, 2], [2, 4], [0, 4]]})
    assert client.get("/api/v1/polygon/contains", params={"x": 1, "y": 3}).json()["contains"] is True
    assert client.get("/api/v1/polygon/contains", params={"x": 3, "y": 3}).json()["contains"] is False


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
                  "implicittreap", "lazysegtree", "tst", "hld", "sparseseg", "convexhull"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
