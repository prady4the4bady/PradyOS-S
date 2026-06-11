"""Phase 82 — tests for the /api/v1/unionfind endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.unionfind import UnionFind
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_uf():
    return TestClient(create_app())


@pytest.fixture()
def client_with_uf():
    return TestClient(create_app(unionfind=UnionFind(10)))


# ── no union-find configured ──────────────────────────────────────────────────

def test_stats_no_uf_returns_error(client_no_uf):
    assert "error" in client_no_uf.get("/api/v1/unionfind").json()


def test_union_no_uf_returns_error(client_no_uf):
    assert "error" in client_no_uf.post("/api/v1/unionfind/union", json={"a": 1, "b": 2}).json()


def test_find_no_uf_returns_error(client_no_uf):
    assert "error" in client_no_uf.post("/api/v1/unionfind/find", json={"a": 1}).json()


def test_connected_no_uf_returns_error(client_no_uf):
    assert "error" in client_no_uf.post("/api/v1/unionfind/connected", json={"a": 1, "b": 2}).json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_keys(client_with_uf):
    data = client_with_uf.get("/api/v1/unionfind").json()
    assert set(data) == {"size", "components", "largest_component"}
    assert data["components"] == 10


# ── union ─────────────────────────────────────────────────────────────────────

def test_union_merges_and_decrements(client_with_uf):
    resp = client_with_uf.post("/api/v1/unionfind/union", json={"a": 1, "b": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["united"] is True
    assert body["components"] == 9


def test_union_already_connected_returns_false(client_with_uf):
    client_with_uf.post("/api/v1/unionfind/union", json={"a": 1, "b": 2})
    assert client_with_uf.post("/api/v1/unionfind/union", json={"a": 1, "b": 2}).json()["united"] is False


def test_union_out_of_bounds_returns_422(client_with_uf):
    assert client_with_uf.post("/api/v1/unionfind/union", json={"a": 1, "b": 99}).status_code == 422


# ── find ──────────────────────────────────────────────────────────────────────

def test_find_returns_root(client_with_uf):
    client_with_uf.post("/api/v1/unionfind/union", json={"a": 3, "b": 4})
    body = client_with_uf.post("/api/v1/unionfind/find", json={"a": 4}).json()
    assert body["root"] == client_with_uf.post("/api/v1/unionfind/find", json={"a": 3}).json()["root"]
    assert body["component_size"] == 2


def test_find_out_of_bounds_returns_422(client_with_uf):
    assert client_with_uf.post("/api/v1/unionfind/find", json={"a": 0}).status_code == 422


# ── connected ─────────────────────────────────────────────────────────────────

def test_connected_true_after_union(client_with_uf):
    client_with_uf.post("/api/v1/unionfind/union", json={"a": 1, "b": 2})
    assert client_with_uf.post("/api/v1/unionfind/connected", json={"a": 1, "b": 2}).json()["connected"] is True


def test_connected_false_for_separate(client_with_uf):
    assert client_with_uf.post("/api/v1/unionfind/connected", json={"a": 1, "b": 5}).json()["connected"] is False


def test_connected_out_of_bounds_returns_422(client_with_uf):
    assert client_with_uf.post("/api/v1/unionfind/connected", json={"a": 1, "b": 11}).status_code == 422


def test_transitivity_via_sequential_unions(client_with_uf):
    client_with_uf.post("/api/v1/unionfind/union", json={"a": 1, "b": 2})
    client_with_uf.post("/api/v1/unionfind/union", json={"a": 2, "b": 3})
    assert client_with_uf.post("/api/v1/unionfind/connected", json={"a": 1, "b": 3}).json()["connected"] is True
    assert client_with_uf.get("/api/v1/unionfind").json()["components"] == 8


def test_union_self_is_noop(client_with_uf):
    resp = client_with_uf.post("/api/v1/unionfind/union", json={"a": 4, "b": 4})
    assert resp.json()["united"] is False
    assert resp.json()["components"] == 10


# ── regression: prior phases' routes still live ───────────────────────────────

def test_prior_phase_routes_still_live(client_no_uf):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client_no_uf.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
