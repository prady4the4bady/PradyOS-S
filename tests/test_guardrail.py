"""Phase 43D — 20 tests for GuardrailGate + ApprovalQueue."""
from __future__ import annotations

import time

import pytest

from pradyos.core.guardrail import ActionRequest, GuardrailGate, RiskLevel
from pradyos.core.approval_queue import (
    ApprovalEntry,
    ApprovalQueue,
    ApprovalStatus,
)
from pradyos.core.decision_journal import DecisionJournal


# ── ActionRequest ─────────────────────────────────────────────────────────────

def test_action_request_required_fields():
    req = ActionRequest(
        id="abc", action="x", risk_level=RiskLevel.LOW,
        payload={}, requested_at=time.time(), reason=None,
    )
    assert req.id == "abc"
    assert req.action == "x"
    assert req.risk_level == RiskLevel.LOW
    assert req.payload == {}
    assert req.requested_at > 0
    assert req.reason is None


def test_action_request_id_non_empty_string():
    gate = GuardrailGate()
    req = gate.submit("noop", RiskLevel.SAFE, {})
    assert isinstance(req.id, str)
    assert len(req.id) > 0


def test_action_request_to_dict_has_all_fields():
    gate = GuardrailGate()
    req = gate.submit("x", RiskLevel.SAFE, {"k": "v"})
    d = req.to_dict()
    for key in ("id", "action", "risk_level", "payload", "requested_at", "reason"):
        assert key in d
    assert d["risk_level"] == "safe"


# ── RiskLevel ─────────────────────────────────────────────────────────────────

def test_risk_level_has_all_values():
    assert RiskLevel.SAFE.value == "safe"
    assert RiskLevel.LOW.value == "low"
    assert RiskLevel.MEDIUM.value == "medium"
    assert RiskLevel.HIGH.value == "high"
    assert RiskLevel.CRITICAL.value == "critical"


# ── GuardrailGate init ────────────────────────────────────────────────────────

def test_gate_init_defaults():
    gate = GuardrailGate()
    assert gate._queue is None
    assert gate._journal is None


# ── submit auto-approve ───────────────────────────────────────────────────────

def test_submit_safe_returns_request_immediately():
    gate = GuardrailGate()
    req = gate.submit("read_log", RiskLevel.SAFE, {})
    assert isinstance(req, ActionRequest)


def test_submit_low_returns_request_immediately():
    gate = GuardrailGate()
    req = gate.submit("ping", RiskLevel.LOW, {})
    assert isinstance(req, ActionRequest)


# ── submit queue ──────────────────────────────────────────────────────────────

def test_submit_medium_adds_to_queue():
    q = ApprovalQueue()
    gate = GuardrailGate(approval_queue=q)
    gate.submit("config_update", RiskLevel.MEDIUM, {})
    assert q.count() == 1


def test_submit_high_adds_to_queue():
    q = ApprovalQueue()
    gate = GuardrailGate(approval_queue=q)
    gate.submit("restart_db", RiskLevel.HIGH, {})
    assert q.count() == 1


# ── submit CRITICAL requires reason ───────────────────────────────────────────

def test_submit_critical_without_reason_raises():
    gate = GuardrailGate()
    with pytest.raises(ValueError, match="reason required"):
        gate.submit("delete_db", RiskLevel.CRITICAL, {})


def test_submit_critical_with_reason_adds_to_queue():
    q = ApprovalQueue()
    gate = GuardrailGate(approval_queue=q)
    gate.submit("delete_db", RiskLevel.CRITICAL, {}, reason="compliance audit")
    assert q.count() == 1


# ── decision_journal integration ──────────────────────────────────────────────

def test_auto_approved_records_to_journal():
    j = DecisionJournal()
    gate = GuardrailGate(decision_journal=j)
    gate.submit("noop", RiskLevel.SAFE, {})
    entries = j.get_entries()
    assert len(entries) == 1
    assert entries[0].decision_type == "auto_approved"


def test_queued_records_to_journal():
    j = DecisionJournal()
    q = ApprovalQueue()
    gate = GuardrailGate(approval_queue=q, decision_journal=j)
    gate.submit("restart", RiskLevel.HIGH, {})
    entries = j.get_entries()
    assert entries[0].decision_type == "pending_approval"


# ── status ────────────────────────────────────────────────────────────────────

def test_gate_status_has_required_keys():
    gate = GuardrailGate()
    s = gate.status()
    assert "auto_approve_levels" in s
    assert "queue_size" in s


def test_gate_status_queue_size_zero_no_queue():
    gate = GuardrailGate()
    assert gate.status()["queue_size"] == 0


# ── ApprovalQueue ─────────────────────────────────────────────────────────────

def test_queue_add_returns_pending_entry():
    q = ApprovalQueue()
    req = ActionRequest(
        id="x1", action="a", risk_level=RiskLevel.MEDIUM,
        payload={}, requested_at=time.time(), reason=None,
    )
    entry = q.add(req)
    assert entry.status == ApprovalStatus.PENDING
    assert entry.id == "x1"


def test_queue_approve_sets_status_approved():
    q = ApprovalQueue()
    req = ActionRequest(id="x", action="a", risk_level=RiskLevel.HIGH,
                        payload={}, requested_at=time.time(), reason=None)
    q.add(req)
    entry = q.approve("x", resolver_note="ok")
    assert entry is not None
    assert entry.status == ApprovalStatus.APPROVED
    assert entry.resolver_note == "ok"


def test_queue_reject_sets_status_rejected():
    q = ApprovalQueue()
    req = ActionRequest(id="y", action="a", risk_level=RiskLevel.HIGH,
                        payload={}, requested_at=time.time(), reason=None)
    q.add(req)
    entry = q.reject("y", resolver_note="too risky")
    assert entry.status == ApprovalStatus.REJECTED


def test_queue_expire_stale_marks_old_entries():
    q = ApprovalQueue(default_timeout=0.001)
    req = ActionRequest(id="z", action="a", risk_level=RiskLevel.HIGH,
                        payload={}, requested_at=time.time(), reason=None)
    q.add(req)
    time.sleep(0.01)
    expired = q.expire_stale()
    assert len(expired) == 1
    assert expired[0].status == ApprovalStatus.EXPIRED


def test_queue_count_returns_correct_total():
    q = ApprovalQueue()
    for i in range(3):
        req = ActionRequest(id=f"k{i}", action="a", risk_level=RiskLevel.MEDIUM,
                            payload={}, requested_at=time.time(), reason=None)
        q.add(req)
    assert q.count() == 3
    assert q.count("pending") == 3
    assert q.count("approved") == 0
