"""Phase 37D — 10 tests for healing monitor endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.healing_monitor import HealingMonitor
from pradyos.core.health_scorecard import HealthScorecard
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_hm():
    return TestClient(create_app())


@pytest.fixture()
def client_with_hm():
    hs = HealthScorecard()
    hm = HealingMonitor(health_scorecard=hs)
    app = create_app(healing_monitor=hm)
    return TestClient(app), hs, hm


# ── GET /api/v1/healer/components ─────────────────────────────────────────────

def test_get_components_returns_200(client_no_hm):
    assert client_no_hm.get("/api/v1/healer/components").status_code == 200


def test_get_components_no_monitor_empty(client_no_hm):
    data = client_no_hm.get("/api/v1/healer/components").json()
    assert data["components"] == []


# ── POST /api/v1/healer/check ─────────────────────────────────────────────────

def test_post_check_returns_200(client_no_hm):
    assert client_no_hm.post("/api/v1/healer/check").status_code == 200


def test_post_check_no_monitor_empty_healed(client_no_hm):
    data = client_no_hm.post("/api/v1/healer/check").json()
    assert data["healed"] == []


# ── GET /api/v1/healer/log ────────────────────────────────────────────────────

def test_get_log_returns_200(client_no_hm):
    assert client_no_hm.get("/api/v1/healer/log").status_code == 200


def test_get_log_no_monitor_empty(client_no_hm):
    data = client_no_hm.get("/api/v1/healer/log").json()
    assert data["events"] == []


# ── healing flow ──────────────────────────────────────────────────────────────

def test_score_above_threshold_no_heal(client_with_hm):
    client, hs, hm = client_with_hm
    hs.update("svc", 90.0)
    hm.register("svc", threshold=50.0, action="restart", repair_fn=lambda: None)
    data = client.post("/api/v1/healer/check").json()
    assert data["healed"] == []


def test_score_below_threshold_one_event(client_with_hm):
    client, hs, hm = client_with_hm
    hs.update("svc", 10.0)
    hm.register("svc", threshold=50.0, action="restart", repair_fn=lambda: None)
    data = client.post("/api/v1/healer/check").json()
    assert len(data["healed"]) == 1
    assert data["healed"][0]["component"] == "svc"
    assert data["healed"][0]["action_taken"] == "restart"


def test_log_has_event_after_healing(client_with_hm):
    client, hs, hm = client_with_hm
    hs.update("svc", 10.0)
    hm.register("svc", threshold=50.0, action="restart", repair_fn=lambda: None)
    client.post("/api/v1/healer/check")
    log = client.get("/api/v1/healer/log").json()
    assert len(log["events"]) == 1


def test_components_reflects_registered(client_with_hm):
    client, _, hm = client_with_hm
    hm.register("svc", 50.0, "restart", lambda: None)
    hm.register("db", 70.0, "reset", lambda: None)
    data = client.get("/api/v1/healer/components").json()
    names = [c["name"] for c in data["components"]]
    assert "svc" in names
    assert "db" in names
