"""Phase 30D — 10 tests for watchpoint endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.watchpoint import WatchpointSystem
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_with_system():
    ws = WatchpointSystem()
    app = create_app(watchpoint_system=ws)
    return TestClient(app), ws


@pytest.fixture()
def client_no_system():
    app = create_app()
    return TestClient(app)


# ── GET /api/v1/watchpoints ───────────────────────────────────────────────────

def test_get_watchpoints_returns_200(client_with_system):
    client, _ = client_with_system
    resp = client.get("/api/v1/watchpoints")
    assert resp.status_code == 200


def test_get_watchpoints_has_required_keys(client_with_system):
    client, _ = client_with_system
    data = client.get("/api/v1/watchpoints").json()
    assert "watchpoints" in data
    assert "status" in data


def test_get_watchpoints_no_system_returns_empty_list(client_no_system):
    data = client_no_system.get("/api/v1/watchpoints").json()
    assert data["watchpoints"] == []


# ── POST /api/v1/watchpoints ──────────────────────────────────────────────────

def test_post_watchpoint_returns_200(client_with_system):
    client, _ = client_with_system
    resp = client.post("/api/v1/watchpoints", json={
        "name": "cpu_high", "metric": "cpu", "operator": "gt", "threshold": 90.0
    })
    assert resp.status_code == 200


def test_post_watchpoint_response_has_fields(client_with_system):
    client, _ = client_with_system
    data = client.post("/api/v1/watchpoints", json={
        "name": "mem_low", "metric": "mem", "operator": "lt", "threshold": 10.0,
        "severity": "critical",
    }).json()
    assert data["name"] == "mem_low"
    assert data["metric"] == "mem"
    assert data["operator"] == "lt"
    assert data["threshold"] == 10.0
    assert data["severity"] == "critical"


def test_post_watchpoint_no_system_returns_error(client_no_system):
    data = client_no_system.post("/api/v1/watchpoints", json={
        "name": "x", "metric": "y", "operator": "gt", "threshold": 1.0
    }).json()
    assert "error" in data


# ── POST /api/v1/watchpoints/check ───────────────────────────────────────────

def test_post_check_returns_200(client_with_system):
    client, _ = client_with_system
    resp = client.post("/api/v1/watchpoints/check", json={"metric": "cpu", "value": 50.0})
    assert resp.status_code == 200


def test_post_check_response_has_alerts_and_count(client_with_system):
    client, _ = client_with_system
    data = client.post("/api/v1/watchpoints/check", json={"metric": "cpu", "value": 50.0}).json()
    assert "alerts" in data
    assert "count" in data


def test_post_check_fires_registered_watchpoint(client_with_system):
    client, ws = client_with_system
    ws.register("cpu_high", metric="cpu", operator="gt", threshold=80.0, severity="critical")
    data = client.post("/api/v1/watchpoints/check", json={"metric": "cpu", "value": 95.0}).json()
    assert data["count"] == 1
    assert data["alerts"][0]["watchpoint_name"] == "cpu_high"
    assert data["alerts"][0]["severity"] == "critical"


def test_post_check_no_system_returns_count_zero(client_no_system):
    data = client_no_system.post("/api/v1/watchpoints/check",
                                 json={"metric": "cpu", "value": 99.0}).json()
    assert data["count"] == 0
    assert data["alerts"] == []
