"""Tests for Phase 7B: metrics_hooks.py"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pradyos.core.metrics import Counter, Gauge, Histogram, MetricsRegistry
from pradyos.core.metrics_hooks import wire_metrics, METRIC_NAMES, _ensure_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_registry() -> MetricsRegistry:
    return MetricsRegistry()


# ---------------------------------------------------------------------------
# 1. wire_metrics returns the registry
# ---------------------------------------------------------------------------

def test_wire_metrics_returns_registry():
    reg = _fresh_registry()
    result = wire_metrics(registry=reg)
    assert result is reg


def test_wire_metrics_uses_singleton_when_none():
    from pradyos.core.metrics import get_registry
    result = wire_metrics()
    assert isinstance(result, MetricsRegistry)


# ---------------------------------------------------------------------------
# 2. All required metrics are registered
# ---------------------------------------------------------------------------

def test_all_metrics_registered():
    reg = _fresh_registry()
    wire_metrics(registry=reg)
    for name in METRIC_NAMES:
        assert reg.get(name) is not None, f"Missing metric: {name}"


# ---------------------------------------------------------------------------
# 3. tasks_submitted increments on submit
# ---------------------------------------------------------------------------

def test_tasks_submitted_counter(tmp_path):
    reg = _fresh_registry()
    kernel = MagicMock()
    kernel.submit = lambda task: MagicMock()
    kernel._run_record = None

    wire_metrics(imperium_kernel=kernel, registry=reg)
    task = MagicMock()

    assert reg.get("tasks_submitted").value == 0
    kernel.submit(task)
    assert reg.get("tasks_submitted").value == 1
    kernel.submit(task)
    assert reg.get("tasks_submitted").value == 2


# ---------------------------------------------------------------------------
# 4. tasks_in_flight gauge inc/dec
# ---------------------------------------------------------------------------

def test_tasks_in_flight_gauge():
    reg = _fresh_registry()
    kernel = MagicMock()
    kernel.submit = lambda task: MagicMock()

    # _run_record that sets state=SUCCEEDED
    def fake_run_record(rec):
        rec.state = "SUCCEEDED"

    kernel._run_record = fake_run_record

    wire_metrics(imperium_kernel=kernel, registry=reg)
    gauge = reg.get("tasks_in_flight")
    assert gauge.value == 0.0

    rec = MagicMock()
    rec.state = "SUCCEEDED"
    kernel._run_record(rec)

    # After completion, in_flight should be back to 0
    assert gauge.value == 0.0


# ---------------------------------------------------------------------------
# 5. tasks_succeeded / tasks_failed counters
# ---------------------------------------------------------------------------

def test_tasks_succeeded_counter():
    reg = _fresh_registry()
    kernel = MagicMock()
    kernel.submit = lambda t: MagicMock()

    def fake_run(rec):
        rec.state = "SUCCEEDED"

    kernel._run_record = fake_run
    wire_metrics(imperium_kernel=kernel, registry=reg)

    rec = MagicMock()
    rec.state = "SUCCEEDED"
    kernel._run_record(rec)

    assert reg.get("tasks_succeeded").value == 1
    assert reg.get("tasks_failed").value == 0


def test_tasks_failed_counter():
    reg = _fresh_registry()
    kernel = MagicMock()
    kernel.submit = lambda t: MagicMock()

    def fake_run(rec):
        rec.state = "FAILED"

    kernel._run_record = fake_run
    wire_metrics(imperium_kernel=kernel, registry=reg)

    rec = MagicMock()
    rec.state = "FAILED"
    kernel._run_record(rec)

    assert reg.get("tasks_failed").value == 1
    assert reg.get("tasks_succeeded").value == 0


# ---------------------------------------------------------------------------
# 6. task_duration_sec histogram observes on terminal state
# ---------------------------------------------------------------------------

def test_task_duration_histogram():
    reg = _fresh_registry()
    kernel = MagicMock()
    kernel.submit = lambda t: MagicMock()

    def fake_run(rec):
        rec.state = "SUCCEEDED"

    kernel._run_record = fake_run
    wire_metrics(imperium_kernel=kernel, registry=reg)

    rec = MagicMock()
    rec.state = "SUCCEEDED"
    kernel._run_record(rec)

    hist = reg.get("task_duration_sec")
    assert isinstance(hist, Histogram)
    assert hist.count == 1
    assert hist.sum_ >= 0.0


# ---------------------------------------------------------------------------
# 7. campaigns_started / campaigns_succeeded / campaigns_failed
# ---------------------------------------------------------------------------

def test_campaign_counters_succeeded():
    reg = _fresh_registry()
    engine = MagicMock()

    async def fake_run(campaign):
        campaign.status = MagicMock()
        campaign.status.__str__ = lambda s: "SUCCEEDED"
        return campaign

    engine.run_campaign = fake_run
    wire_metrics(campaign_engine=engine, registry=reg)

    campaign = MagicMock()
    campaign.status = MagicMock()
    campaign.status.__str__ = lambda s: "SUCCEEDED"

    asyncio.run(engine.run_campaign(campaign))

    assert reg.get("campaigns_started").value == 1
    assert reg.get("campaigns_succeeded").value == 1
    assert reg.get("campaigns_failed").value == 0


def test_campaign_counters_failed():
    reg = _fresh_registry()
    engine = MagicMock()

    async def fake_run(campaign):
        campaign.status = MagicMock()
        campaign.status.__str__ = lambda s: "FAILED"
        return campaign

    engine.run_campaign = fake_run
    wire_metrics(campaign_engine=engine, registry=reg)

    campaign = MagicMock()
    campaign.status = MagicMock()
    campaign.status.__str__ = lambda s: "FAILED"

    asyncio.run(engine.run_campaign(campaign))

    assert reg.get("campaigns_started").value == 1
    assert reg.get("campaigns_failed").value == 1
    assert reg.get("campaigns_succeeded").value == 0


# ---------------------------------------------------------------------------
# 8. oracle_plans_ok / oracle_plans_error
# ---------------------------------------------------------------------------

def test_oracle_plans_ok():
    reg = _fresh_registry()
    planner = MagicMock()

    async def fake_plan(task):
        plan = MagicMock()
        plan.ok = True
        plan.error = None
        return plan

    planner.plan = fake_plan
    wire_metrics(oracle_planner=planner, registry=reg)

    task = MagicMock()
    asyncio.run(planner.plan(task))

    assert reg.get("oracle_plans_ok").value == 1
    assert reg.get("oracle_plans_error").value == 0


def test_oracle_plans_error():
    reg = _fresh_registry()
    planner = MagicMock()

    async def fake_plan_err(task):
        plan = MagicMock()
        plan.ok = False
        plan.error = "Ollama timeout"
        return plan

    planner.plan = fake_plan_err
    wire_metrics(oracle_planner=planner, registry=reg)

    task = MagicMock()
    asyncio.run(planner.plan(task))

    assert reg.get("oracle_plans_error").value == 1
    assert reg.get("oracle_plans_ok").value == 0


# ---------------------------------------------------------------------------
# 9. ensure_metrics is idempotent
# ---------------------------------------------------------------------------

def test_ensure_metrics_idempotent():
    reg = _fresh_registry()
    m1 = _ensure_metrics(reg)
    m2 = _ensure_metrics(reg)
    # Same objects
    assert m1["tasks_submitted"] is m2["tasks_submitted"]
    assert m1["tasks_in_flight"] is m2["tasks_in_flight"]


# ---------------------------------------------------------------------------
# 10. None subsystems are safely skipped
# ---------------------------------------------------------------------------

def test_none_subsystems_safe():
    reg = _fresh_registry()
    result = wire_metrics(
        imperium_kernel=None,
        campaign_engine=None,
        oracle_planner=None,
        warden_grid=None,
        registry=reg,
    )
    assert result is reg
    # Metrics still registered
    assert reg.get("tasks_submitted") is not None
