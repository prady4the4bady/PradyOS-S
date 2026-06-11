"""Phase 31D — 10 tests for signal aggregator endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.signal_aggregator import SignalAggregator
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_with_agg():
    sa = SignalAggregator()
    app = create_app(signal_aggregator=sa)
    return TestClient(app), sa


@pytest.fixture()
def client_no_agg():
    app = create_app()
    return TestClient(app)


# ── GET /api/v1/signals ───────────────────────────────────────────────────────

def test_get_signals_returns_200(client_with_agg):
    client, _ = client_with_agg
    resp = client.get("/api/v1/signals")
    assert resp.status_code == 200


def test_get_signals_has_signals_key(client_with_agg):
    client, _ = client_with_agg
    data = client.get("/api/v1/signals").json()
    assert "signals" in data


def test_get_signals_no_agg_returns_empty(client_no_agg):
    data = client_no_agg.get("/api/v1/signals").json()
    assert data["signals"] == []


# ── POST /api/v1/signals ──────────────────────────────────────────────────────

def test_post_signal_returns_200(client_with_agg):
    client, _ = client_with_agg
    resp = client.post("/api/v1/signals", json={"name": "cpu", "value": 55.0})
    assert resp.status_code == 200


def test_post_signal_response_has_value_and_recorded_at(client_with_agg):
    client, _ = client_with_agg
    data = client.post("/api/v1/signals", json={"name": "mem", "value": 77.5}).json()
    assert data["value"] == 77.5
    assert "recorded_at" in data


def test_post_signal_no_agg_returns_error(client_no_agg):
    data = client_no_agg.post("/api/v1/signals", json={"name": "x", "value": 1.0}).json()
    assert "error" in data


# ── GET /api/v1/signals/{name} ────────────────────────────────────────────────

def test_get_signal_by_name_returns_200(client_with_agg):
    client, _ = client_with_agg
    resp = client.get("/api/v1/signals/cpu")
    assert resp.status_code == 200


def test_get_signal_by_name_has_required_keys(client_with_agg):
    client, _ = client_with_agg
    data = client.get("/api/v1/signals/cpu").json()
    assert "points" in data
    assert "count" in data
    assert "stats" in data


def test_post_then_get_reflects_point(client_with_agg):
    client, _ = client_with_agg
    client.post("/api/v1/signals", json={"name": "disk", "value": 42.0})
    data = client.get("/api/v1/signals/disk").json()
    assert data["count"] == 1
    assert data["points"][0]["value"] == 42.0
    assert data["stats"] is not None
    assert data["stats"]["mean"] == 42.0


def test_get_unknown_signal_returns_200_empty_points(client_with_agg):
    client, _ = client_with_agg
    data = client.get("/api/v1/signals/does_not_exist").json()
    assert data["points"] == []
    assert data["count"] == 0
    assert data["stats"] is None
