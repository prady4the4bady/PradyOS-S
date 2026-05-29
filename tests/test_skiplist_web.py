"""Phase 78 — tests for the /api/v1/skiplist endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.skiplist import SkipList
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_sl():
    return TestClient(create_app())


@pytest.fixture()
def client_with_sl():
    return TestClient(create_app(skiplist=SkipList(seed=1)))


# ── no skip list configured ───────────────────────────────────────────────────

def test_stats_no_sl_returns_error(client_no_sl):
    assert "error" in client_no_sl.get("/api/v1/skiplist").json()


def test_insert_no_sl_returns_error(client_no_sl):
    assert "error" in client_no_sl.post("/api/v1/skiplist/insert", json={"key": "a", "value": 1}).json()


def test_search_no_sl_returns_error(client_no_sl):
    assert "error" in client_no_sl.post("/api/v1/skiplist/search", json={"key": "a"}).json()


def test_range_no_sl_returns_error(client_no_sl):
    assert "error" in client_no_sl.post("/api/v1/skiplist/range", json={"lo": "a", "hi": "z"}).json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_has_expected_keys(client_with_sl):
    data = client_with_sl.get("/api/v1/skiplist").json()
    for key in ("size", "level_count", "max_level"):
        assert key in data


# ── insert ────────────────────────────────────────────────────────────────────

def test_insert_sets_size(client_with_sl):
    resp = client_with_sl.post("/api/v1/skiplist/insert", json={"key": "a", "value": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["size"] == 1
    assert body["value"] == 100


def test_insert_missing_key_returns_422(client_with_sl):
    resp = client_with_sl.post("/api/v1/skiplist/insert", json={"value": 1})
    assert resp.status_code == 422
    assert "error" in resp.json()


# ── search ────────────────────────────────────────────────────────────────────

def test_search_found(client_with_sl):
    client_with_sl.post("/api/v1/skiplist/insert", json={"key": "a", "value": 42})
    body = client_with_sl.post("/api/v1/skiplist/search", json={"key": "a"}).json()
    assert body["found"] is True
    assert body["value"] == 42


def test_search_absent(client_with_sl):
    body = client_with_sl.post("/api/v1/skiplist/search", json={"key": "ghost"}).json()
    assert body["found"] is False
    assert body["value"] is None


def test_search_missing_key_returns_422(client_with_sl):
    assert client_with_sl.post("/api/v1/skiplist/search", json={}).status_code == 422


# ── range ─────────────────────────────────────────────────────────────────────

def test_range_inclusive_sorted(client_with_sl):
    for k in ("e", "a", "c", "b", "d"):
        client_with_sl.post("/api/v1/skiplist/insert", json={"key": k, "value": k.upper()})
    body = client_with_sl.post("/api/v1/skiplist/range", json={"lo": "b", "hi": "d"}).json()
    assert body["count"] == 3
    assert body["results"] == [["b", "B"], ["c", "C"], ["d", "D"]]


def test_range_empty_when_lo_gt_hi(client_with_sl):
    client_with_sl.post("/api/v1/skiplist/insert", json={"key": "a", "value": 1})
    body = client_with_sl.post("/api/v1/skiplist/range", json={"lo": "z", "hi": "a"}).json()
    assert body["results"] == []


def test_range_missing_bounds_returns_422(client_with_sl):
    assert client_with_sl.post("/api/v1/skiplist/range", json={"lo": "a"}).status_code == 422


# ── round-trip ────────────────────────────────────────────────────────────────

def test_insert_search_range_round_trip(client_with_sl):
    for i in range(5):
        client_with_sl.post("/api/v1/skiplist/insert", json={"key": f"{i:02d}", "value": i})
    assert client_with_sl.post("/api/v1/skiplist/search", json={"key": "03"}).json()["value"] == 3
    rng = client_with_sl.post("/api/v1/skiplist/range", json={"lo": "01", "hi": "03"}).json()
    assert [k for k, _ in rng["results"]] == ["01", "02", "03"]
