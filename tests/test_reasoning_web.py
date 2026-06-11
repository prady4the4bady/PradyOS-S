"""Phase 45D — 10 tests for reasoning endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.reasoning_engine import ReasoningEngine
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_engine():
    return TestClient(create_app())


@pytest.fixture()
def client_with_engine():
    e = ReasoningEngine()
    app = create_app(reasoning_engine=e)
    return TestClient(app), e


def _rule(**overrides) -> dict:
    base = {
        "trigger": "restart",
        "action": "restart_service db",
        "risk_level": "medium",
        "rationale": "recover",
        "preconditions": {"db_healthy": False},
    }
    base.update(overrides)
    return base


# ── status ────────────────────────────────────────────────────────────────────

def test_get_status_returns_200(client_no_engine):
    assert client_no_engine.get("/api/v1/reason/status").status_code == 200


def test_status_no_engine_zero(client_no_engine):
    data = client_no_engine.get("/api/v1/reason/status").json()
    assert data["rule_count"] == 0


# ── rules ─────────────────────────────────────────────────────────────────────

def test_post_rule_adds_increments_count(client_with_engine):
    client, _ = client_with_engine
    data = client.post("/api/v1/reason/rules", json=_rule()).json()
    assert data["rule_count"] == 1


def test_post_rule_missing_key_400(client_with_engine):
    client, _ = client_with_engine
    bad = {"trigger": "x", "action": "y"}  # missing required keys
    resp = client.post("/api/v1/reason/rules", json=bad)
    assert resp.status_code == 400


# ── reason ────────────────────────────────────────────────────────────────────

def test_post_reason_no_engine_400(client_no_engine):
    resp = client_no_engine.post("/api/v1/reason",
                                  json={"goal": "x", "state": {}})
    assert resp.status_code == 400


def test_post_reason_missing_goal_400(client_with_engine):
    client, _ = client_with_engine
    resp = client.post("/api/v1/reason", json={"state": {}})
    assert resp.status_code == 400


def test_post_reason_returns_goal_key(client_with_engine):
    client, _ = client_with_engine
    data = client.post("/api/v1/reason",
                       json={"goal": "anything", "state": {}}).json()
    assert data["goal"] == "anything"


def test_post_reason_returns_steps_key(client_with_engine):
    client, _ = client_with_engine
    data = client.post("/api/v1/reason",
                       json={"goal": "x", "state": {}}).json()
    assert "steps" in data


def test_post_reason_returns_confidence_float(client_with_engine):
    client, _ = client_with_engine
    data = client.post("/api/v1/reason",
                       json={"goal": "x", "state": {}}).json()
    assert isinstance(data["confidence"], float)


# ── full flow ─────────────────────────────────────────────────────────────────

def test_full_flow_rule_then_reason(client_with_engine):
    client, _ = client_with_engine
    client.post("/api/v1/reason/rules", json=_rule())
    data = client.post("/api/v1/reason",
                       json={"goal": "restart the db", "state": {"db_healthy": False}}).json()
    assert len(data["steps"]) == 1
    assert data["steps"][0]["action"] == "restart_service db"
    assert data["confidence"] == 1.0
