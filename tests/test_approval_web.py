"""Phase 43E — 10 tests for guardrail + approvals endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.guardrail import GuardrailGate, RiskLevel
from pradyos.core.approval_queue import ApprovalQueue
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_gate():
    return TestClient(create_app())


@pytest.fixture()
def client_with_gate():
    q = ApprovalQueue()
    g = GuardrailGate(approval_queue=q)
    app = create_app(guardrail_gate=g, approval_queue=q)
    return TestClient(app), g, q


# ── guardrail status ──────────────────────────────────────────────────────────

def test_guardrail_status_returns_200(client_no_gate):
    assert client_no_gate.get("/api/v1/guardrail/status").status_code == 200


def test_guardrail_status_no_gate_empty_levels(client_no_gate):
    data = client_no_gate.get("/api/v1/guardrail/status").json()
    assert data["auto_approve_levels"] == []


# ── guardrail submit ──────────────────────────────────────────────────────────

def test_submit_safe_auto_approved_response(client_with_gate):
    client, _, q = client_with_gate
    resp = client.post("/api/v1/guardrail/submit", json={
        "action": "read", "risk_level": "safe", "payload": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "safe"
    # SAFE → auto-approved, NOT added to queue
    assert q.count() == 0


def test_submit_medium_has_id_and_queues(client_with_gate):
    client, _, q = client_with_gate
    data = client.post("/api/v1/guardrail/submit", json={
        "action": "config_update", "risk_level": "medium", "payload": {"x": 1},
    }).json()
    assert "id" in data
    assert q.count() == 1


def test_submit_invalid_risk_returns_400(client_with_gate):
    client, _, _ = client_with_gate
    resp = client.post("/api/v1/guardrail/submit", json={
        "action": "x", "risk_level": "bogus", "payload": {},
    })
    assert resp.status_code == 400


# ── approvals list ────────────────────────────────────────────────────────────

def test_approvals_list_returns_entries_key(client_with_gate):
    client, _, _ = client_with_gate
    data = client.get("/api/v1/approvals").json()
    assert "entries" in data


# ── approve / reject ──────────────────────────────────────────────────────────

def test_approve_returns_approved_entry(client_with_gate):
    client, _, q = client_with_gate
    sub = client.post("/api/v1/guardrail/submit", json={
        "action": "x", "risk_level": "high", "payload": {},
    }).json()
    entry_id = sub["id"]
    resp = client.post(f"/api/v1/approvals/{entry_id}/approve", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_reject_returns_rejected_entry(client_with_gate):
    client, _, _ = client_with_gate
    sub = client.post("/api/v1/guardrail/submit", json={
        "action": "y", "risk_level": "high", "payload": {},
    }).json()
    entry_id = sub["id"]
    resp = client.post(f"/api/v1/approvals/{entry_id}/reject",
                       json={"resolver_note": "no"})
    assert resp.json()["status"] == "rejected"


# ── expire ────────────────────────────────────────────────────────────────────

def test_expire_returns_count():
    q = ApprovalQueue(default_timeout=0.001)
    g = GuardrailGate(approval_queue=q)
    client = TestClient(create_app(guardrail_gate=g, approval_queue=q))
    client.post("/api/v1/guardrail/submit", json={
        "action": "x", "risk_level": "high", "payload": {},
    })
    import time as _t
    _t.sleep(0.01)
    data = client.post("/api/v1/approvals/expire").json()
    assert data["expired"] == 1


# ── full flow ─────────────────────────────────────────────────────────────────

def test_full_flow_submit_high_approve_list_shows_approved(client_with_gate):
    client, _, _ = client_with_gate
    sub = client.post("/api/v1/guardrail/submit", json={
        "action": "restart_db", "risk_level": "high", "payload": {"db": "main"},
    }).json()
    entry_id = sub["id"]
    client.post(f"/api/v1/approvals/{entry_id}/approve", json={})
    data = client.get("/api/v1/approvals?status=approved").json()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["id"] == entry_id
    assert data["entries"][0]["status"] == "approved"
