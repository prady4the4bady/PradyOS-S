"""Phase 34D — 10 tests for integration bus status endpoint in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.integration_bus import SovereignBus
from pradyos.core.signal_aggregator import SignalAggregator
from pradyos.core.watchpoint import WatchpointSystem
from pradyos.core.decision_journal import DecisionJournal
from pradyos.core.bus_inspector import BusInspector
from pradyos.core.capability_registry import CapabilityRegistry
from pradyos.core.health_scorecard import HealthScorecard
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_bus():
    return TestClient(create_app())


def _client_with_bus(**modules) -> tuple[TestClient, SovereignBus]:
    bus = SovereignBus(**modules)
    app = create_app(integration_bus=bus)
    return TestClient(app), bus


# ── GET /api/v1/integration/status ────────────────────────────────────────────

def test_get_status_returns_200(client_no_bus):
    assert client_no_bus.get("/api/v1/integration/status").status_code == 200


def test_get_status_no_bus_fallback(client_no_bus):
    data = client_no_bus.get("/api/v1/integration/status").json()
    assert data["wired"] == {}
    assert data["wire_count"] == 0


def test_get_status_with_bus_has_keys():
    client, _ = _client_with_bus()
    data = client.get("/api/v1/integration/status").json()
    assert "wired" in data
    assert "wire_count" in data


def test_get_status_wire_count_zero_empty_bus():
    client, _ = _client_with_bus()
    data = client.get("/api/v1/integration/status").json()
    assert data["wire_count"] == 0


def test_get_status_wire_count_one():
    client, _ = _client_with_bus(signal_aggregator=SignalAggregator())
    data = client.get("/api/v1/integration/status").json()
    assert data["wire_count"] == 1


def test_get_status_wire_count_six():
    client, _ = _client_with_bus(
        signal_aggregator=SignalAggregator(),
        watchpoint_system=WatchpointSystem(),
        decision_journal=DecisionJournal(),
        bus_inspector=BusInspector(),
        capability_registry=CapabilityRegistry(),
        health_scorecard=HealthScorecard(),
    )
    data = client.get("/api/v1/integration/status").json()
    assert data["wire_count"] == 6


def test_get_status_wired_dict_has_all_six_keys():
    client, _ = _client_with_bus()
    wired = client.get("/api/v1/integration/status").json()["wired"]
    for key in ("signal_aggregator", "watchpoint_system", "decision_journal",
                "bus_inspector", "capability_registry", "health_scorecard"):
        assert key in wired, f"Missing key: {key}"


def test_get_status_wired_values_are_booleans():
    client, _ = _client_with_bus(signal_aggregator=SignalAggregator())
    wired = client.get("/api/v1/integration/status").json()["wired"]
    for v in wired.values():
        assert isinstance(v, bool)


def test_get_status_reflects_actual_wiring():
    client, _ = _client_with_bus(signal_aggregator=SignalAggregator())
    wired = client.get("/api/v1/integration/status").json()["wired"]
    assert wired["signal_aggregator"] is True
    assert wired["watchpoint_system"] is False


def test_get_status_no_bus_returns_200_gracefully(client_no_bus):
    resp = client_no_bus.get("/api/v1/integration/status")
    assert resp.status_code == 200
    assert resp.json()["wire_count"] == 0
