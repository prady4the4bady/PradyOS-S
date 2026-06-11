"""Phase 153 — tests for the /api/v1/prquadtree endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.pr_quadtree import PRQuadtree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    q = PRQuadtree(0, 0, 100, 100)
    for (pid, x, y) in [("a", 10, 10), ("b", 50, 50), ("c", 90, 90)]:
        q.insert(pid, x, y)
    return TestClient(create_app(pr_quadtree=q))


# ── insert ────────────────────────────────────────────────────────────────────────────────

def test_insert_returns_num_points(client):
    body = client.post("/api/v1/prquadtree/insert", json={"point_id": "p", "x": 5, "y": 5}).json()
    assert body["num_points"] == 1


def test_insert_missing_422(client):
    assert client.post("/api/v1/prquadtree/insert", json={"point_id": "p", "x": 5}).status_code == 422


def test_insert_out_of_bounds_422(client):
    resp = client.post("/api/v1/prquadtree/insert", json={"point_id": "p", "x": 99999, "y": 5})
    assert resp.status_code == 422 and "error" in resp.json()


def test_insert_non_num_422(client):
    resp = client.post("/api/v1/prquadtree/insert", json={"point_id": "p", "x": "z", "y": 5})
    assert resp.status_code == 422 and "error" in resp.json()


# ── delete ────────────────────────────────────────────────────────────────────────────────

def test_delete_present(filled_client):
    body = filled_client.post("/api/v1/prquadtree/delete", json={"point_id": "b"}).json()
    assert body["deleted"] is True and body["num_points"] == 2


def test_delete_absent(filled_client):
    body = filled_client.post("/api/v1/prquadtree/delete", json={"point_id": "zzz"}).json()
    assert body["deleted"] is False and body["num_points"] == 3


def test_delete_missing_422(client):
    assert client.post("/api/v1/prquadtree/delete", json={}).status_code == 422


# ── search ───────────────────────────────────────────────────────────────────────────────

def test_search_hit(filled_client):
    assert filled_client.get("/api/v1/prquadtree/search", params={"x": 10, "y": 10}).json()["point_id"] == "a"


def test_search_miss(filled_client):
    assert filled_client.get("/api/v1/prquadtree/search", params={"x": 33, "y": 33}).json()["point_id"] is None


# ── range_query ──────────────────────────────────────────────────────────────────────────

def test_range_query(filled_client):
    body = filled_client.get("/api/v1/prquadtree/range_query",
                             params={"x_min": 0, "y_min": 0, "x_max": 60, "y_max": 60}).json()
    assert body["ids"] == ["a", "b"] and body["count"] == 2


def test_range_query_full(filled_client):
    body = filled_client.get("/api/v1/prquadtree/range_query",
                             params={"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100}).json()
    assert body["count"] == 3


def test_range_inverted_422(filled_client):
    resp = filled_client.get("/api/v1/prquadtree/range_query",
                             params={"x_min": 60, "y_min": 60, "x_max": 10, "y_max": 10})
    assert resp.status_code == 422 and "error" in resp.json()


# ── nearest ──────────────────────────────────────────────────────────────────────────────

def test_nearest(filled_client):
    assert filled_client.get("/api/v1/prquadtree/nearest", params={"x": 95, "y": 95}).json()["nearest"] == "c"


def test_nearest_empty_null(client):
    assert client.get("/api/v1/prquadtree/nearest", params={"x": 5, "y": 5}).json()["nearest"] is None


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/prquadtree/stats").json()) == {"num_points", "num_nodes", "max_depth_reached"}


def test_stats_after_insert(filled_client):
    assert filled_client.get("/api/v1/prquadtree/stats").json()["num_points"] == 3


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/prquadtree/reset").json()
    assert body["num_points"] == 0 and body["num_nodes"] == 1


# ── workflow ──────────────────────────────────────────────────────────────────────────────

def test_full_workflow(client):
    for pid, x, y in (("p1", 10, 10), ("p2", 20, 20), ("p3", 900, 900)):
        client.post("/api/v1/prquadtree/insert", json={"point_id": pid, "x": x, "y": y})
    rng = client.get("/api/v1/prquadtree/range_query",
                     params={"x_min": 0, "y_min": 0, "x_max": 50, "y_max": 50}).json()
    assert rng["ids"] == ["p1", "p2"]
    assert client.get("/api/v1/prquadtree/nearest", params={"x": 0, "y": 0}).json()["nearest"] == "p1"
    client.post("/api/v1/prquadtree/delete", json={"point_id": "p1"})
    assert client.get("/api/v1/prquadtree/search", params={"x": 10, "y": 10}).json()["point_id"] is None
    assert client.get("/api/v1/prquadtree/nearest", params={"x": 0, "y": 0}).json()["nearest"] == "p2"


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
                  "suffixautomaton", "veb"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
