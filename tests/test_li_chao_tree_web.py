"""Phase 148 — tests for the /api/v1/lichao endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.li_chao_tree import LiChaoTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    t = LiChaoTree(-100, 100, "min")
    for (m, b) in [(1, 0), (-1, 0), (0, 5)]:
        t.add_line(m, b)
    return TestClient(create_app(li_chao_tree=t))


# ── add_line ─────────────────────────────────────────────────────────────────────────────

def test_add_line_returns_num_lines(client):
    body = client.post("/api/v1/lichao/add_line", json={"m": 2, "b": 3}).json()
    assert body["num_lines"] == 1


def test_add_line_missing_422(client):
    assert client.post("/api/v1/lichao/add_line", json={"m": 2}).status_code == 422


def test_add_line_non_num_422(client):
    resp = client.post("/api/v1/lichao/add_line", json={"m": "x", "b": 3})
    assert resp.status_code == 422 and "error" in resp.json()


# ── add_lines (batch) ────────────────────────────────────────────────────────────────────

def test_add_lines_batch(client):
    body = client.post("/api/v1/lichao/add_lines",
                       json={"lines": [[1, 2], [3, 4], [5, 6]]}).json()
    assert body["added"] == 3 and body["num_lines"] == 3


def test_add_lines_bad_shape_422(client):
    assert client.post("/api/v1/lichao/add_lines", json={"lines": [[1, 2], [3]]}).status_code == 422


def test_add_lines_non_num_422(client):
    resp = client.post("/api/v1/lichao/add_lines", json={"lines": [[1, 2], ["x", 4]]})
    assert resp.status_code == 422 and "error" in resp.json()


# ── query ────────────────────────────────────────────────────────────────────────────────

def test_query(filled_client):
    assert filled_client.get("/api/v1/lichao/query", params={"x": 100}).json()["value"] == -100


def test_query_min_value(filled_client):
    assert filled_client.get("/api/v1/lichao/query", params={"x": 0}).json()["value"] == 0


def test_query_negative_x(filled_client):
    assert filled_client.get("/api/v1/lichao/query", params={"x": -100}).json()["value"] == -100


def test_query_empty_null(client):
    assert client.get("/api/v1/lichao/query", params={"x": 5}).json()["value"] is None


def test_query_out_of_domain_422(filled_client):
    resp = filled_client.get("/api/v1/lichao/query", params={"x": 999})
    assert resp.status_code == 422 and "error" in resp.json()


def test_query_non_int_422(client):
    assert client.get("/api/v1/lichao/query", params={"x": "abc"}).status_code == 422


# ── stats ─────────────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/lichao/stats").json()) == {"num_lines", "x_min", "x_max", "mode", "nodes"}


def test_stats_defaults(client):
    s = client.get("/api/v1/lichao/stats").json()
    assert s["num_lines"] == 0 and s["x_min"] == 0 and s["x_max"] == 1_000_000 and s["mode"] == "min"


def test_stats_after_add(filled_client):
    assert filled_client.get("/api/v1/lichao/stats").json()["num_lines"] == 3


# ── reset ─────────────────────────────────────────────────────────────────────────────────

def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/lichao/reset", json={}).json()
    assert body["num_lines"] == 0


def test_reset_reconfigure(client):
    body = client.request("DELETE", "/api/v1/lichao/reset",
                          json={"x_min": -5, "x_max": 5, "mode": "max"}).json()
    assert body["x_min"] == -5 and body["x_max"] == 5 and body["mode"] == "max"


def test_reset_bad_mode_422(client):
    resp = client.request("DELETE", "/api/v1/lichao/reset", json={"mode": "median"})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/lichao/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────────

def test_max_mode_via_reset(client):
    client.request("DELETE", "/api/v1/lichao/reset", json={"x_min": 0, "x_max": 100, "mode": "max"})
    client.post("/api/v1/lichao/add_line", json={"m": 1, "b": 0})
    client.post("/api/v1/lichao/add_line", json={"m": -1, "b": 100})
    assert client.get("/api/v1/lichao/query", params={"x": 0}).json()["value"] == 100
    assert client.get("/api/v1/lichao/query", params={"x": 50}).json()["value"] == 50


def test_add_then_query(client):
    client.post("/api/v1/lichao/add_lines", json={"lines": [[2, 3], [0, 42]]})
    assert client.get("/api/v1/lichao/query", params={"x": 0}).json()["value"] == 3
    assert client.get("/api/v1/lichao/query", params={"x": 1000}).json()["value"] == 42


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
                  "fenwick2d", "sqrtdecomp"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
