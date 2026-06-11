"""Phase 81 — tests for the /api/v1/segtree endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.segtree import SegmentTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_seg():
    return TestClient(create_app())


@pytest.fixture()
def client_sum():
    return TestClient(create_app(segtree=SegmentTree(10, "sum")))


@pytest.fixture()
def client_min():
    return TestClient(create_app(segtree=SegmentTree(10, "min")))


@pytest.fixture()
def client_max():
    return TestClient(create_app(segtree=SegmentTree(10, "max")))


def _fill(client, values):
    for i, v in enumerate(values, start=1):
        client.post("/api/v1/segtree/update", json={"index": i, "value": v})


# ── no tree configured ────────────────────────────────────────────────────────

def test_stats_no_seg_returns_error(client_no_seg):
    assert "error" in client_no_seg.get("/api/v1/segtree").json()


def test_update_no_seg_returns_error(client_no_seg):
    assert "error" in client_no_seg.post("/api/v1/segtree/update", json={"index": 1, "value": 1}).json()


def test_query_no_seg_returns_error(client_no_seg):
    assert "error" in client_no_seg.post("/api/v1/segtree/query", json={"lo": 1, "hi": 5}).json()


def test_point_no_seg_returns_error(client_no_seg):
    assert "error" in client_no_seg.post("/api/v1/segtree/point", json={"index": 1}).json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_keys_and_mode(client_min):
    data = client_min.get("/api/v1/segtree").json()
    assert set(data) == {"size", "mode", "aggregate"}
    assert data["mode"] == "min"


# ── update ────────────────────────────────────────────────────────────────────

def test_update_reflects_in_aggregate(client_sum):
    resp = client_sum.post("/api/v1/segtree/update", json={"index": 3, "value": 5})
    assert resp.status_code == 200
    assert resp.json()["aggregate"] == 5


def test_update_out_of_bounds_returns_422(client_sum):
    assert client_sum.post("/api/v1/segtree/update", json={"index": 99, "value": 1}).status_code == 422


def test_update_bad_value_returns_422(client_sum):
    assert client_sum.post("/api/v1/segtree/update", json={"index": 1, "value": "x"}).status_code == 422


# ── query (with mode) ─────────────────────────────────────────────────────────

def test_query_sum_mode(client_sum):
    _fill(client_sum, [1, 2, 3, 4, 5])
    body = client_sum.post("/api/v1/segtree/query", json={"lo": 2, "hi": 4}).json()
    assert body["mode"] == "sum"
    assert body["result"] == 2 + 3 + 4


def test_query_min_mode(client_min):
    _fill(client_min, [3, -2, 5, -7, 1])
    body = client_min.post("/api/v1/segtree/query", json={"lo": 1, "hi": 5}).json()
    assert body["mode"] == "min"
    assert body["result"] == -7


def test_query_max_mode(client_max):
    _fill(client_max, [3, -2, 5, -7, 1])
    body = client_max.post("/api/v1/segtree/query", json={"lo": 1, "hi": 5}).json()
    assert body["mode"] == "max"
    assert body["result"] == 5


def test_query_boundary_single_and_full(client_sum):
    _fill(client_sum, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert client_sum.post("/api/v1/segtree/query", json={"lo": 1, "hi": 1}).json()["result"] == 1
    assert client_sum.post("/api/v1/segtree/query", json={"lo": 1, "hi": 10}).json()["result"] == 55


def test_query_out_of_bounds_returns_422(client_sum):
    assert client_sum.post("/api/v1/segtree/query", json={"lo": 0, "hi": 5}).status_code == 422


def test_query_lo_gt_hi_returns_422(client_sum):
    assert client_sum.post("/api/v1/segtree/query", json={"lo": 7, "hi": 3}).status_code == 422


# ── point ─────────────────────────────────────────────────────────────────────

def test_point_returns_value(client_sum):
    client_sum.post("/api/v1/segtree/update", json={"index": 4, "value": 17})
    assert client_sum.post("/api/v1/segtree/point", json={"index": 4}).json()["value"] == 17


def test_point_out_of_bounds_returns_422(client_sum):
    assert client_sum.post("/api/v1/segtree/point", json={"index": 0}).status_code == 422


# ── round-trip ────────────────────────────────────────────────────────────────

def test_update_query_point_round_trip(client_max):
    _fill(client_max, [5, 1, 9, 3, 7, 2, 8, 4, 6, 0])
    assert client_max.post("/api/v1/segtree/query", json={"lo": 1, "hi": 10}).json()["result"] == 9
    assert client_max.post("/api/v1/segtree/point", json={"index": 3}).json()["value"] == 9


# ── regression: prior phases' routes still live ───────────────────────────────

def test_prior_phase_routes_still_live(client_no_seg):
    # Each prior data-structure route should respond (200 + JSON error when its
    # component isn't injected), proving the patch chain left them intact.
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree"):
        resp = client_no_seg.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
