"""Phase 35D — 11 tests for reactor endpoints + integration_bus chain."""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from pradyos.core.reactor import ReactorEngine
from pradyos.core.integration_bus import SovereignBus
from pradyos.core.signal_aggregator import SignalAggregator
from pradyos.core.watchpoint import WatchpointSystem
from pradyos.core.decision_journal import DecisionJournal
from pradyos.sovereign_web import create_app


@dataclass
class _StubEntry:
    decision_type: str
    rationale: str
    outcome: str


@pytest.fixture()
def client_no_reactor():
    return TestClient(create_app())


@pytest.fixture()
def client_with_reactor():
    eng = ReactorEngine()
    app = create_app(reactor_engine=eng)
    return TestClient(app), eng


# ── GET /api/v1/reactor/rules ─────────────────────────────────────────────────

def test_get_rules_returns_200(client_with_reactor):
    client, _ = client_with_reactor
    assert client.get("/api/v1/reactor/rules").status_code == 200


def test_get_rules_no_reactor_empty(client_no_reactor):
    data = client_no_reactor.get("/api/v1/reactor/rules").json()
    assert data["rules"] == []


# ── POST /api/v1/reactor/rules ────────────────────────────────────────────────

def test_post_rule_returns_200(client_with_reactor):
    client, _ = client_with_reactor
    resp = client.post("/api/v1/reactor/rules",
                       json={"decision_type": "watchpoint_alert", "action": "log"})
    assert resp.status_code == 200


def test_post_rule_no_reactor_returns_error(client_no_reactor):
    data = client_no_reactor.post("/api/v1/reactor/rules",
                                   json={"decision_type": "x", "action": "log"}).json()
    assert "error" in data


def test_post_rule_response_has_required_fields(client_with_reactor):
    client, _ = client_with_reactor
    data = client.post("/api/v1/reactor/rules",
                       json={"decision_type": "watchpoint_alert", "action": "escalate"}).json()
    assert "rule_id" in data
    assert data["decision_type"] == "watchpoint_alert"
    assert data["action"] == "escalate"


# ── DELETE /api/v1/reactor/rules/{rule_id} ────────────────────────────────────

def test_delete_rule_returns_deleted_true(client_with_reactor):
    client, eng = client_with_reactor
    rule = eng.add_rule("watchpoint_alert", "log")
    resp = client.delete(f"/api/v1/reactor/rules/{rule.rule_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_delete_rule_unknown_returns_404(client_with_reactor):
    client, _ = client_with_reactor
    resp = client.delete("/api/v1/reactor/rules/phantom")
    assert resp.status_code == 404


# ── GET /api/v1/reactor/log ───────────────────────────────────────────────────

def test_get_log_returns_200(client_with_reactor):
    client, _ = client_with_reactor
    assert client.get("/api/v1/reactor/log").status_code == 200


def test_get_log_no_reactor_empty(client_no_reactor):
    data = client_no_reactor.get("/api/v1/reactor/log").json()
    assert data["reactions"] == []


# ── full flow via direct react() ──────────────────────────────────────────────

def test_full_flow_add_rule_react_log_has_entry(client_with_reactor):
    client, eng = client_with_reactor
    client.post("/api/v1/reactor/rules",
                json={"decision_type": "watchpoint_alert", "action": "log"})
    eng.react(_StubEntry(decision_type="watchpoint_alert",
                         rationale="signal=cpu value=99",
                         outcome="alert:cpu_high"))
    data = client.get("/api/v1/reactor/log").json()
    assert len(data["reactions"]) == 1
    assert data["reactions"][0]["action"] == "log"


# ── integration_bus chain: watchpoint → journal → reactor ─────────────────────

def test_integration_bus_watchpoint_fires_reactor():
    sa = SignalAggregator()
    ws = WatchpointSystem()
    ws.register("cpu_high", metric="cpu", operator="gt",
                threshold=80.0, severity="critical")
    dj = DecisionJournal()
    eng = ReactorEngine()
    eng.add_rule("watchpoint_alert", "escalate")
    bus = SovereignBus(
        signal_aggregator=sa,
        watchpoint_system=ws,
        decision_journal=dj,
        reactor_engine=eng,
    )
    bus.record_signal("cpu", 95.0)
    log = eng.get_log()
    assert len(log) == 1
    assert log[0].action == "escalate"
    assert log[0].decision_type == "watchpoint_alert"
