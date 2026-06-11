"""Phase 12 — GET /api/v1/dashboard endpoint tests (10 tests).

Uses FastAPI TestClient to exercise the dashboard HTTP endpoint
wired into the sovereign web app via the ``observability_dashboard``
parameter of ``create_app()``.

Covers:
    1.  GET /api/v1/dashboard returns HTTP 200
    2.  Response body has "bus_events" key
    3.  Response body has "quarantine" key
    4.  Response body has "system_health" key
    5.  quarantine field reflects kernel state
    6.  system_health contains "status" field
    7.  system_health "status" is a valid value (ok/degraded/critical)
    8.  bus_events is a list
    9.  system_health contains "active_tasks" and "dead_letter_count"
    10. Response Content-Type is application/json
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from pradyos.aurora_throne.dashboard import DashboardSnapshot, ObservabilityDashboard
from pradyos.core.bus import EventBus
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_snapshot(
    bus_events: list | None = None,
    quarantine: list | None = None,
    status: str = "ok",
    active_tasks: int = 0,
    dead_letter_count: int = 0,
    last_event_ts: float | None = None,
) -> DashboardSnapshot:
    return DashboardSnapshot(
        bus_events=bus_events or [],
        quarantine=quarantine or [],
        system_health={
            "status": status,
            "active_tasks": active_tasks,
            "dead_letter_count": dead_letter_count,
            "last_event_ts": last_event_ts,
        },
    )


def _make_dashboard_mock(snapshot: DashboardSnapshot) -> MagicMock:
    dash = MagicMock(spec=ObservabilityDashboard)
    dash.get_live_snapshot.return_value = snapshot
    return dash


def _client(snapshot: DashboardSnapshot | None = None) -> TestClient:
    """Create a TestClient with an optional mock ObservabilityDashboard."""
    dash_mock = _make_dashboard_mock(snapshot) if snapshot is not None else None
    app = create_app(observability_dashboard=dash_mock)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Test 1: GET /api/v1/dashboard returns HTTP 200
# ---------------------------------------------------------------------------

def test_dashboard_endpoint_returns_200():
    client = _client(_make_snapshot())
    resp = client.get("/api/v1/dashboard")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 2: Response body has "bus_events" key
# ---------------------------------------------------------------------------

def test_dashboard_response_has_bus_events_key():
    client = _client(_make_snapshot())
    resp = client.get("/api/v1/dashboard")
    data = resp.json()
    assert "bus_events" in data


# ---------------------------------------------------------------------------
# Test 3: Response body has "quarantine" key
# ---------------------------------------------------------------------------

def test_dashboard_response_has_quarantine_key():
    client = _client(_make_snapshot())
    resp = client.get("/api/v1/dashboard")
    data = resp.json()
    assert "quarantine" in data


# ---------------------------------------------------------------------------
# Test 4: Response body has "system_health" key
# ---------------------------------------------------------------------------

def test_dashboard_response_has_system_health_key():
    client = _client(_make_snapshot())
    resp = client.get("/api/v1/dashboard")
    data = resp.json()
    assert "system_health" in data


# ---------------------------------------------------------------------------
# Test 5: quarantine field reflects kernel state
# ---------------------------------------------------------------------------

def test_dashboard_quarantine_reflects_kernel_state():
    snap = _make_snapshot(quarantine=["task-q1", "task-q2"])
    client = _client(snap)
    resp = client.get("/api/v1/dashboard")
    data = resp.json()
    assert set(data["quarantine"]) == {"task-q1", "task-q2"}


# ---------------------------------------------------------------------------
# Test 6: system_health contains "status" field
# ---------------------------------------------------------------------------

def test_dashboard_health_status_field_present():
    client = _client(_make_snapshot())
    resp = client.get("/api/v1/dashboard")
    data = resp.json()
    assert "status" in data["system_health"]


# ---------------------------------------------------------------------------
# Test 7: system_health "status" is a valid value
# ---------------------------------------------------------------------------

def test_dashboard_health_status_is_valid_value():
    for status in ("ok", "degraded", "critical"):
        snap = _make_snapshot(status=status)
        client = _client(snap)
        resp = client.get("/api/v1/dashboard")
        data = resp.json()
        assert data["system_health"]["status"] == status


# ---------------------------------------------------------------------------
# Test 8: bus_events is a list
# ---------------------------------------------------------------------------

def test_dashboard_bus_events_is_list():
    events = [
        {"topic": "system.self_heal", "payload": {"task_id": "t-1"}, "ts": 1.0},
        {"topic": "imperium.task_queued", "payload": {"task_id": "t-2"}, "ts": 2.0},
    ]
    snap = _make_snapshot(bus_events=events)
    client = _client(snap)
    resp = client.get("/api/v1/dashboard")
    data = resp.json()
    assert isinstance(data["bus_events"], list)
    assert len(data["bus_events"]) == 2


# ---------------------------------------------------------------------------
# Test 9: system_health contains active_tasks and dead_letter_count
# ---------------------------------------------------------------------------

def test_dashboard_system_health_has_required_keys():
    snap = _make_snapshot(active_tasks=3, dead_letter_count=1, status="degraded")
    client = _client(snap)
    resp = client.get("/api/v1/dashboard")
    data = resp.json()
    health = data["system_health"]
    assert "active_tasks" in health
    assert "dead_letter_count" in health
    assert health["active_tasks"] == 3
    assert health["dead_letter_count"] == 1


# ---------------------------------------------------------------------------
# Test 10: Response Content-Type is application/json
# ---------------------------------------------------------------------------

def test_dashboard_returns_json_content_type():
    client = _client(_make_snapshot())
    resp = client.get("/api/v1/dashboard")
    assert "application/json" in resp.headers.get("content-type", "")
