"""Phase 80 — tests for the /api/v1/fenwick endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.fenwick import FenwickTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_fw():
    return TestClient(create_app())


@pytest.fixture()
def client_with_fw():
    return TestClient(create_app(fenwick=FenwickTree(10)))


# ── no tree configured ────────────────────────────────────────────────────────

def test_stats_no_fw_returns_error(client_no_fw):
    assert "error" in client_no_fw.get("/api/v1/fenwick").json()


def test_update_no_fw_returns_error(client_no_fw):
    assert "error" in client_no_fw.post("/api/v1/fenwick/update", json={"index": 1, "delta": 1}).json()


def test_query_no_fw_returns_error(client_no_fw):
    assert "error" in client_no_fw.post("/api/v1/fenwick/query", json={"lo": 1, "hi": 5}).json()


def test_point_no_fw_returns_error(client_no_fw):
    assert "error" in client_no_fw.post("/api/v1/fenwick/point", json={"index": 1}).json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_has_expected_keys(client_with_fw):
    data = client_with_fw.get("/api/v1/fenwick").json()
    assert set(data) == {"size", "total"}


# ── update ────────────────────────────────────────────────────────────────────

def test_update_reflects_in_total(client_with_fw):
    resp = client_with_fw.post("/api/v1/fenwick/update", json={"index": 3, "delta": 5})
    assert resp.status_code == 200
    assert resp.json()["total"] == 5


def test_update_negative_delta(client_with_fw):
    client_with_fw.post("/api/v1/fenwick/update", json={"index": 2, "delta": 10})
    client_with_fw.post("/api/v1/fenwick/update", json={"index": 2, "delta": -4})
    assert client_with_fw.post("/api/v1/fenwick/point", json={"index": 2}).json()["value"] == 6


def test_update_out_of_bounds_returns_422(client_with_fw):
    assert client_with_fw.post("/api/v1/fenwick/update", json={"index": 99, "delta": 1}).status_code == 422


def test_update_bad_delta_returns_422(client_with_fw):
    assert client_with_fw.post("/api/v1/fenwick/update", json={"index": 1, "delta": "x"}).status_code == 422


# ── query (range_sum) ─────────────────────────────────────────────────────────

def test_query_range_sum(client_with_fw):
    for i in range(1, 6):
        client_with_fw.post("/api/v1/fenwick/update", json={"index": i, "delta": i})
    body = client_with_fw.post("/api/v1/fenwick/query", json={"lo": 2, "hi": 4}).json()
    assert body["sum"] == 2 + 3 + 4


def test_query_out_of_bounds_returns_422(client_with_fw):
    assert client_with_fw.post("/api/v1/fenwick/query", json={"lo": 0, "hi": 5}).status_code == 422


def test_query_lo_gt_hi_returns_422(client_with_fw):
    assert client_with_fw.post("/api/v1/fenwick/query", json={"lo": 7, "hi": 3}).status_code == 422


# ── point ─────────────────────────────────────────────────────────────────────

def test_point_returns_value(client_with_fw):
    client_with_fw.post("/api/v1/fenwick/update", json={"index": 4, "delta": 17})
    assert client_with_fw.post("/api/v1/fenwick/point", json={"index": 4}).json()["value"] == 17


def test_point_out_of_bounds_returns_422(client_with_fw):
    assert client_with_fw.post("/api/v1/fenwick/point", json={"index": 0}).status_code == 422


# ── round-trip ────────────────────────────────────────────────────────────────

def test_update_query_point_round_trip(client_with_fw):
    for i in range(1, 11):
        client_with_fw.post("/api/v1/fenwick/update", json={"index": i, "delta": i * 2})
    assert client_with_fw.get("/api/v1/fenwick").json()["total"] == sum(i * 2 for i in range(1, 11))
    assert client_with_fw.post("/api/v1/fenwick/query", json={"lo": 1, "hi": 10}).json()["sum"] == 110
    assert client_with_fw.post("/api/v1/fenwick/point", json={"index": 5}).json()["value"] == 10
