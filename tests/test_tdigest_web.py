"""Phase 79 — tests for the /api/v1/tdigest endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.tdigest import TDigest
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_td():
    return TestClient(create_app())


@pytest.fixture()
def client_with_td():
    return TestClient(create_app(tdigest=TDigest()))


def _seed(client, values):
    for v in values:
        client.post("/api/v1/tdigest/add", json={"value": v})


# ── no digest configured ──────────────────────────────────────────────────────

def test_stats_no_td_returns_error(client_no_td):
    assert "error" in client_no_td.get("/api/v1/tdigest").json()


def test_add_no_td_returns_error(client_no_td):
    assert "error" in client_no_td.post("/api/v1/tdigest/add", json={"value": 1}).json()


def test_percentile_no_td_returns_error(client_no_td):
    assert "error" in client_no_td.post("/api/v1/tdigest/percentile", json={"q": 50}).json()


def test_merge_no_td_returns_error(client_no_td):
    assert "error" in client_no_td.post("/api/v1/tdigest/merge", json={"values": []}).json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_has_expected_keys(client_with_td):
    data = client_with_td.get("/api/v1/tdigest").json()
    for key in ("count", "centroids", "min", "max", "max_centroids", "compression"):
        assert key in data


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_increments_count(client_with_td):
    resp = client_with_td.post("/api/v1/tdigest/add", json={"value": 42})
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_add_with_weight(client_with_td):
    resp = client_with_td.post("/api/v1/tdigest/add", json={"value": 5, "weight": 10})
    assert resp.status_code == 200
    assert resp.json()["count"] == 10


def test_add_non_numeric_value_returns_422(client_with_td):
    assert client_with_td.post("/api/v1/tdigest/add", json={"value": "x"}).status_code == 422


def test_add_bad_weight_returns_422(client_with_td):
    assert client_with_td.post("/api/v1/tdigest/add", json={"value": 1, "weight": 0}).status_code == 422


# ── percentile ────────────────────────────────────────────────────────────────

def test_percentile_extremes(client_with_td):
    _seed(client_with_td, [10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert client_with_td.post("/api/v1/tdigest/percentile", json={"q": 0}).json()["value"] == 10
    assert client_with_td.post("/api/v1/tdigest/percentile", json={"q": 100}).json()["value"] == 100


def test_percentile_middle_in_range(client_with_td):
    _seed(client_with_td, [10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    mid = client_with_td.post("/api/v1/tdigest/percentile", json={"q": 50}).json()["value"]
    assert 10 <= mid <= 100


def test_percentile_out_of_range_returns_422(client_with_td):
    _seed(client_with_td, [1, 2, 3])
    assert client_with_td.post("/api/v1/tdigest/percentile", json={"q": 150}).status_code == 422


def test_percentile_on_empty_returns_400(client_with_td):
    resp = client_with_td.post("/api/v1/tdigest/percentile", json={"q": 50})
    assert resp.status_code == 400
    assert "error" in resp.json()


# ── merge ─────────────────────────────────────────────────────────────────────

def test_merge_increases_count(client_with_td):
    _seed(client_with_td, [1, 2, 3])
    resp = client_with_td.post("/api/v1/tdigest/merge", json={"values": [4, 5, 6, 7], "q": 50})
    assert resp.status_code == 200
    body = resp.json()
    assert body["merged"] is True
    assert body["count"] == 7  # 3 + 4
    assert "percentile" in body


def test_merge_invalid_values_returns_422(client_with_td):
    assert client_with_td.post("/api/v1/tdigest/merge", json={"values": "nope"}).status_code == 422


# ── round-trip ────────────────────────────────────────────────────────────────

def test_add_percentile_round_trip(client_with_td):
    _seed(client_with_td, list(range(1, 101)))
    p99 = client_with_td.post("/api/v1/tdigest/percentile", json={"q": 99}).json()["value"]
    assert 90 <= p99 <= 100
