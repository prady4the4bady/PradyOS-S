"""Phase 139 — tests for the /api/v1/kdtree endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.kd_tree import KDTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    return TestClient(create_app(kd_tree=KDTree([(0, 0), (3, 4), (10, 10)], dim=2)))


# ── build ──────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/kdtree/build", json={"points": [[0, 0], [3, 4], [10, 10]]}).json()
    assert body["size"] == 3 and body["dim"] == 2


def test_build_missing_points_422(client):
    assert client.post("/api/v1/kdtree/build", json={}).status_code == 422


def test_build_wrong_dim_422(client):
    resp = client.post("/api/v1/kdtree/build", json={"points": [[1, 2, 3]], "dim": 2})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_3d(client):
    body = client.post("/api/v1/kdtree/build",
                       json={"points": [[1, 2, 3], [4, 5, 6]], "dim": 3}).json()
    assert body["dim"] == 3 and body["size"] == 2


def test_build_non_numeric_422(client):
    resp = client.post("/api/v1/kdtree/build", json={"points": [[1, "x"]], "dim": 2})
    assert resp.status_code == 422 and "error" in resp.json()


# ── nearest ──────────────────────────────────────────────────────────────────────────────

def test_nearest(built_client):
    body = built_client.post("/api/v1/kdtree/nearest", json={"point": [3, 3]}).json()
    assert body["nearest"] == [3, 4] and abs(body["distance"] - 1.0) < 1e-9


def test_nearest_empty(client):
    body = client.post("/api/v1/kdtree/nearest", json={"point": [1, 2]}).json()
    assert body["nearest"] is None and body["distance"] is None


def test_nearest_missing_point_422(built_client):
    assert built_client.post("/api/v1/kdtree/nearest", json={}).status_code == 422


def test_nearest_wrong_dim_422(built_client):
    resp = built_client.post("/api/v1/kdtree/nearest", json={"point": [1]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── range ────────────────────────────────────────────────────────────────────────────────

def test_range(built_client):
    body = built_client.post("/api/v1/kdtree/range", json={"lo": [0, 0], "hi": [5, 5]}).json()
    assert body["points"] == [[0, 0], [3, 4]] and body["count"] == 2


def test_range_empty(built_client):
    body = built_client.post("/api/v1/kdtree/range", json={"lo": [20, 20], "hi": [30, 30]}).json()
    assert body["points"] == [] and body["count"] == 0


def test_range_missing_422(built_client):
    assert built_client.post("/api/v1/kdtree/range", json={"lo": [0, 0]}).status_code == 422


def test_range_lo_gt_hi_422(built_client):
    resp = built_client.post("/api/v1/kdtree/range", json={"lo": [5, 5], "hi": [1, 1]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/kdtree/stats").json()) == {"size", "dim", "height"}


def test_stats_defaults(client):
    s = client.get("/api/v1/kdtree/stats").json()
    assert s["size"] == 0 and s["dim"] == 2


def test_stats_after_build(built_client):
    assert built_client.get("/api/v1/kdtree/stats").json()["size"] == 3


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    body = built_client.request("DELETE", "/api/v1/kdtree/reset").json()
    assert body["size"] == 0


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/kdtree/reset").status_code == 200


# ── 3-D round-trip ────────────────────────────────────────────────────────────────────────

def test_build_then_nearest_3d(client):
    client.post("/api/v1/kdtree/build", json={"points": [[0, 0, 0], [10, 10, 10]], "dim": 3})
    body = client.post("/api/v1/kdtree/nearest", json={"point": [1, 1, 1]}).json()
    assert body["nearest"] == [0, 0, 0]


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
                  "skewheap", "intervaltree", "sparsetable"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
