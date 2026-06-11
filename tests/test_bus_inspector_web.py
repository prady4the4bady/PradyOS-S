"""Phase 27: BusInspector web endpoint tests (10 tests)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.bus_inspector import BusInspector
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_no_insp() -> TestClient:
    """TestClient with no BusInspector wired in."""
    return TestClient(create_app())


@pytest.fixture
def insp() -> BusInspector:
    return BusInspector(max_size=100)


@pytest.fixture
def client_with_insp(insp: BusInspector) -> TestClient:
    """TestClient with a live BusInspector."""
    return TestClient(create_app(bus_inspector=insp))


# ---------------------------------------------------------------------------
# /api/v1/bus/events — basic
# ---------------------------------------------------------------------------

def test_bus_events_returns_200(client_no_insp: TestClient) -> None:
    """GET /api/v1/bus/events returns HTTP 200."""
    r = client_no_insp.get("/api/v1/bus/events")
    assert r.status_code == 200


def test_bus_events_response_has_required_keys(client_no_insp: TestClient) -> None:
    """Response body has 'events' and 'count' keys."""
    data = client_no_insp.get("/api/v1/bus/events").json()
    assert "events" in data
    assert "count" in data


def test_bus_events_no_inspector_events_is_empty(client_no_insp: TestClient) -> None:
    """When no inspector: events is []."""
    data = client_no_insp.get("/api/v1/bus/events").json()
    assert data["events"] == []


def test_bus_events_no_inspector_count_is_zero(client_no_insp: TestClient) -> None:
    """When no inspector: count is 0."""
    data = client_no_insp.get("/api/v1/bus/events").json()
    assert data["count"] == 0


# ---------------------------------------------------------------------------
# /api/v1/bus/stats — basic
# ---------------------------------------------------------------------------

def test_bus_stats_returns_200(client_no_insp: TestClient) -> None:
    """GET /api/v1/bus/stats returns HTTP 200."""
    r = client_no_insp.get("/api/v1/bus/stats")
    assert r.status_code == 200


def test_bus_stats_has_required_keys(client_no_insp: TestClient) -> None:
    """Stats response contains total_events, buffer_size, max_size, topics."""
    data = client_no_insp.get("/api/v1/bus/stats").json()
    for key in ("total_events", "buffer_size", "max_size", "topics"):
        assert key in data, f"Missing key: {key}"


def test_bus_stats_no_inspector_total_events_zero(client_no_insp: TestClient) -> None:
    """When no inspector: total_events = 0."""
    data = client_no_insp.get("/api/v1/bus/stats").json()
    assert data["total_events"] == 0


# ---------------------------------------------------------------------------
# /api/v1/bus/events — with live inspector
# ---------------------------------------------------------------------------

def test_bus_events_with_inspector_returns_recorded(
    client_with_insp: TestClient,
    insp: BusInspector,
) -> None:
    """record() then GET /api/v1/bus/events returns that event."""
    insp.record("test.phase27", {"x": 42})
    data = client_with_insp.get("/api/v1/bus/events").json()
    assert data["count"] == 1
    assert data["events"][0]["topic"] == "test.phase27"
    assert data["events"][0]["payload"] == {"x": 42}


def test_bus_events_topic_filter(
    client_with_insp: TestClient,
    insp: BusInspector,
) -> None:
    """GET /api/v1/bus/events?topic=x filters to matching topic only."""
    insp.record("alpha", {"n": 1})
    insp.record("beta", {"n": 2})
    insp.record("alpha", {"n": 3})
    data = client_with_insp.get("/api/v1/bus/events", params={"topic": "alpha"}).json()
    assert data["count"] == 2
    assert all(e["topic"] == "alpha" for e in data["events"])


def test_bus_events_limit_query_param(
    client_with_insp: TestClient,
    insp: BusInspector,
) -> None:
    """GET /api/v1/bus/events?limit=1 returns at most 1 event."""
    for i in range(5):
        insp.record("t", {"i": i})
    data = client_with_insp.get("/api/v1/bus/events", params={"limit": 1}).json()
    assert len(data["events"]) == 1
    assert data["count"] == 1
