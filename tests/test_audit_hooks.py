"""Tests for Phase 7A: audit_hooks.py"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

from pradyos.core.audit import AuditCategory, AuditEvent, EventAuditLog
from pradyos.core.audit_hooks import wire_audit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log(tmp_path: Path) -> EventAuditLog:
    return EventAuditLog(path=tmp_path / "audit_hooks_test.jsonl")


# ---------------------------------------------------------------------------
# 1. wire_audit returns an EventAuditLog
# ---------------------------------------------------------------------------

def test_wire_audit_returns_log(tmp_path):
    log = _make_log(tmp_path)
    result = wire_audit(audit_log=log)
    assert result is log


def test_wire_audit_creates_log_when_none():
    result = wire_audit()
    assert isinstance(result, EventAuditLog)


# ---------------------------------------------------------------------------
# 2. Imperium kernel — submit hook fires
# ---------------------------------------------------------------------------

def test_imperium_submit_hook(tmp_path):
    log = _make_log(tmp_path)

    kernel = MagicMock()
    submitted = {}

    def fake_submit(task):
        rec = MagicMock()
        rec.spec = task
        rec.state = "QUEUED"
        return rec

    kernel.submit = fake_submit
    kernel._run_record = None  # skip _run_record wiring

    wire_audit(imperium_kernel=kernel, audit_log=log)
    task = MagicMock()
    task.task_id = "t-001"
    task.intent = "install nginx"
    task.kind = "shell"

    kernel.submit(task)

    events = log.tail(10)
    assert any(e.action == "task_queued" for e in events)
    queued = next(e for e in events if e.action == "task_queued")
    assert queued.category == AuditCategory.SOVEREIGN
    assert queued.payload["task_id"] == "t-001"


# ---------------------------------------------------------------------------
# 3. Imperium kernel — approve hook fires
# ---------------------------------------------------------------------------

def test_imperium_approve_hook(tmp_path):
    log = _make_log(tmp_path)
    kernel = MagicMock()
    kernel.approve = lambda task_id, approver="sovereign": True
    kernel._run_record = None

    wire_audit(imperium_kernel=kernel, audit_log=log)
    kernel.approve("t-002", "prady")

    events = log.tail(10)
    assert any(e.action == "task_approved" for e in events)
    ev = next(e for e in events if e.action == "task_approved")
    assert ev.payload["task_id"] == "t-002"
    assert ev.payload["approved"] is True


# ---------------------------------------------------------------------------
# 4. Imperium kernel — reject hook fires
# ---------------------------------------------------------------------------

def test_imperium_reject_hook(tmp_path):
    log = _make_log(tmp_path)
    kernel = MagicMock()
    kernel.reject = lambda task_id, approver="sovereign", reason="": True
    kernel._run_record = None

    wire_audit(imperium_kernel=kernel, audit_log=log)
    kernel.reject("t-003", "prady", "policy violation")

    events = log.tail(10)
    assert any(e.action == "task_rejected" for e in events)
    ev = next(e for e in events if e.action == "task_rejected")
    assert ev.payload["reason"] == "policy violation"


# ---------------------------------------------------------------------------
# 5. CampaignEngine — create_campaign hook fires
# ---------------------------------------------------------------------------

def test_campaign_create_hook(tmp_path):
    log = _make_log(tmp_path)

    engine = MagicMock()
    campaign = MagicMock()
    campaign.campaign_id = "c-001"
    engine.create_campaign = lambda name, intent, tasks, **kw: campaign

    wire_audit(campaign_engine=engine, audit_log=log)
    engine.create_campaign("Deploy nginx", "install nginx", [], submitted_by="test")

    events = log.tail(10)
    assert any(e.action == "campaign_created" for e in events)
    ev = next(e for e in events if e.action == "campaign_created")
    assert ev.category == AuditCategory.CAMPAIGN
    assert ev.payload["name"] == "Deploy nginx"


# ---------------------------------------------------------------------------
# 6. CampaignEngine — run_campaign hook fires (async)
# ---------------------------------------------------------------------------

def test_campaign_run_hook(tmp_path):
    log = _make_log(tmp_path)

    engine = MagicMock()

    async def fake_run(campaign):
        campaign.status = MagicMock()
        campaign.status.__str__ = lambda s: "SUCCEEDED"
        return campaign

    engine.run_campaign = fake_run
    engine._execute_node = None

    wire_audit(campaign_engine=engine, audit_log=log)

    campaign = MagicMock()
    campaign.campaign_id = "c-002"
    campaign.name = "Test Campaign"

    asyncio.run(engine.run_campaign(campaign))

    events = log.tail(10)
    actions = [e.action for e in events]
    assert "campaign_started" in actions
    # Terminal event (succeeded or failed or terminal)
    assert any(a in actions for a in ["campaign_succeeded", "campaign_failed", "campaign_terminal"])


# ---------------------------------------------------------------------------
# 7. TitanExecutor — execute hook fires (dispatched + completed)
# ---------------------------------------------------------------------------

def test_titan_execute_hook(tmp_path):
    log = _make_log(tmp_path)

    executor = MagicMock()
    result = MagicMock()
    result.succeeded = True
    result.exit_code = 0
    result.timed_out = False
    result.escalated = False
    result.error = None
    executor.execute = lambda instr: result

    wire_audit(titan_executor=executor, audit_log=log)

    instr = MagicMock()
    instr.instruction_id = "i-001"
    instr.intent = "echo hello"
    instr.command = "echo hello"

    executor.execute(instr)

    events = log.tail(10)
    actions = [e.action for e in events]
    assert "instruction_dispatched" in actions
    assert "instruction_completed" in actions
    for ev in events:
        assert ev.category == AuditCategory.WARDEN


# ---------------------------------------------------------------------------
# 8. OraclePlanner — plan hook fires (async)
# ---------------------------------------------------------------------------

def test_oracle_plan_hook(tmp_path):
    log = _make_log(tmp_path)

    planner = MagicMock()

    async def fake_plan(task):
        plan = MagicMock()
        plan.ok = True
        plan.error = None
        plan.requires_approval = False
        plan.steps = []
        return plan

    planner.plan = fake_plan

    wire_audit(oracle_planner=planner, audit_log=log)

    task = MagicMock()
    task.task_id = "t-010"
    task.intent = "research best practices"

    asyncio.run(planner.plan(task))

    events = log.tail(10)
    assert any(e.action == "plan_produced" for e in events)
    ev = next(e for e in events if e.action == "plan_produced")
    assert ev.category == AuditCategory.ORACLE
    assert ev.payload["task_id"] == "t-010"


# ---------------------------------------------------------------------------
# 9. Oracle plan error hook
# ---------------------------------------------------------------------------

def test_oracle_plan_error_hook(tmp_path):
    log = _make_log(tmp_path)

    planner = MagicMock()

    async def fake_plan_err(task):
        plan = MagicMock()
        plan.ok = False
        plan.error = "Ollama unavailable"
        plan.requires_approval = False
        plan.steps = []
        return plan

    planner.plan = fake_plan_err

    wire_audit(oracle_planner=planner, audit_log=log)

    task = MagicMock()
    task.task_id = "t-011"
    task.intent = "some task"

    asyncio.run(planner.plan(task))

    events = log.tail(10)
    assert any(e.action == "plan_errored" for e in events)


# ---------------------------------------------------------------------------
# 10. None subsystems are safely skipped
# ---------------------------------------------------------------------------

def test_none_subsystems_safe(tmp_path):
    log = _make_log(tmp_path)
    # Should not raise
    result = wire_audit(
        imperium_kernel=None,
        campaign_engine=None,
        titan_executor=None,
        oracle_planner=None,
        audit_log=log,
    )
    assert result is log
    assert len(log.tail(10)) == 0


# ---------------------------------------------------------------------------
# 11. Multiple hooks accumulate events
# ---------------------------------------------------------------------------

def test_multiple_hooks_accumulate(tmp_path):
    log = _make_log(tmp_path)

    kernel = MagicMock()
    kernel.submit = lambda task: MagicMock(spec=task, state="QUEUED")
    kernel.approve = lambda task_id, approver="sovereign": True
    kernel._run_record = None

    wire_audit(imperium_kernel=kernel, audit_log=log)

    task = MagicMock()
    task.task_id = "t-multi"
    task.intent = "multi test"
    task.kind = "shell"

    kernel.submit(task)
    kernel.approve("t-multi")
    kernel.approve("t-multi2")

    events = log.tail(20)
    assert len(events) >= 3
