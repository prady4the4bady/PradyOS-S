"""Metrics wiring — Phase 7B.

Registers and auto-increments standard metrics by attaching lightweight
hooks to the four primary subsystems (Imperium, CampaignEngine,
OraclePlanner, WardenGrid) via the same composition pattern used by
audit_hooks.py — no monkey-patching of stdlib, only instance-attribute
shadowing on the provided objects.

Metrics registered
------------------
  Counter  tasks_submitted
  Counter  tasks_succeeded
  Counter  tasks_failed
  Counter  campaigns_started
  Counter  campaigns_succeeded
  Counter  campaigns_failed
  Counter  oracle_plans_ok
  Counter  oracle_plans_error
  Gauge    tasks_in_flight
  Histogram task_duration_sec  (buckets: 1, 5, 15, 60, 300)

The MetricsRegistry singleton (``pradyos.core.metrics.get_registry``) is
used by default so that ``GET /api/metrics`` sees the same counters.

Windows-safe: no signals, no AF_UNIX, no fork.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import Any

from pradyos.core.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    get_registry,
)

log = logging.getLogger("pradyos.core.metrics_hooks")

__all__ = ["wire_metrics", "METRIC_NAMES"]

METRIC_NAMES = (
    "tasks_submitted",
    "tasks_succeeded",
    "tasks_failed",
    "campaigns_started",
    "campaigns_succeeded",
    "campaigns_failed",
    "oracle_plans_ok",
    "oracle_plans_error",
    "tasks_in_flight",
    "task_duration_sec",
)


# ---------------------------------------------------------------------------
# Registry setup
# ---------------------------------------------------------------------------

def _ensure_metrics(registry: MetricsRegistry) -> dict[str, Any]:
    """Create metrics in the registry if they don't exist yet.

    Idempotent — safe to call multiple times.
    """
    def _counter(name: str, desc: str = "") -> Counter:
        existing = registry.get(name)
        if existing is not None and isinstance(existing, Counter):
            return existing
        m = Counter(name, desc)
        registry.register(m)
        return m

    def _gauge(name: str, desc: str = "") -> Gauge:
        existing = registry.get(name)
        if existing is not None and isinstance(existing, Gauge):
            return existing
        m = Gauge(name, desc)
        registry.register(m)
        return m

    def _histogram(name: str, desc: str = "", buckets: list[float] | None = None) -> Histogram:
        existing = registry.get(name)
        if existing is not None and isinstance(existing, Histogram):
            return existing
        m = Histogram(name, desc, buckets=buckets)
        registry.register(m)
        return m

    return {
        "tasks_submitted":     _counter("tasks_submitted",    "Total tasks submitted to Imperium"),
        "tasks_succeeded":     _counter("tasks_succeeded",    "Tasks completed successfully"),
        "tasks_failed":        _counter("tasks_failed",       "Tasks that failed"),
        "campaigns_started":   _counter("campaigns_started",  "Campaigns started"),
        "campaigns_succeeded": _counter("campaigns_succeeded","Campaigns that succeeded"),
        "campaigns_failed":    _counter("campaigns_failed",   "Campaigns that failed"),
        "oracle_plans_ok":     _counter("oracle_plans_ok",    "Oracle plans produced successfully"),
        "oracle_plans_error":  _counter("oracle_plans_error", "Oracle plans that errored"),
        "tasks_in_flight":     _gauge("tasks_in_flight",      "Tasks currently running"),
        "task_duration_sec":   _histogram(
            "task_duration_sec",
            "Task execution duration in seconds",
            buckets=[1.0, 5.0, 15.0, 60.0, 300.0],
        ),
    }


# ---------------------------------------------------------------------------
# Internal wrapping helpers
# ---------------------------------------------------------------------------

def _wrap_sync(obj: Any, method_name: str, before: Any, after: Any) -> None:
    original = getattr(obj, method_name)

    @functools.wraps(original)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        if before is not None:
            try:
                before(args, kwargs)
            except Exception as e:  # noqa: BLE001
                log.debug("metrics hook before() failed: %s", e)
        exc: Exception | None = None
        result: Any = None
        try:
            result = original(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            exc = e
        try:
            after(result, args, kwargs, exc)
        except Exception as e:  # noqa: BLE001
            log.debug("metrics hook after() failed: %s", e)
        if exc is not None:
            raise exc
        return result

    setattr(obj, method_name, _wrapper)


# ---------------------------------------------------------------------------
# Public wiring function
# ---------------------------------------------------------------------------

def wire_metrics(
    imperium_kernel: Any | None = None,
    campaign_engine: Any | None = None,
    oracle_planner: Any | None = None,
    warden_grid: Any | None = None,
    registry: MetricsRegistry | None = None,
) -> MetricsRegistry:
    """Attach metrics counters/gauges/histograms to each subsystem.

    Parameters
    ----------
    imperium_kernel : Imperium instance — tracks task lifecycle metrics.
    campaign_engine : CampaignEngine instance — tracks campaign metrics.
    oracle_planner  : OraclePlanner instance — tracks plan metrics.
    warden_grid     : WardenGrid/Monitor instance (reserved for future hooks).
    registry        : MetricsRegistry to use. Defaults to the global singleton.

    Returns the registry used.
    """
    if registry is None:
        registry = get_registry()

    metrics = _ensure_metrics(registry)

    _wire_imperium_metrics(imperium_kernel, metrics)
    _wire_campaign_metrics(campaign_engine, metrics)
    _wire_oracle_metrics(oracle_planner, metrics)
    # warden_grid: future hooks go here (currently observable via bus events)

    log.info("Metrics hooks wired (registry has %d metrics)", len(metrics))
    return registry


# ---------------------------------------------------------------------------
# Per-subsystem wiring
# ---------------------------------------------------------------------------

def _wire_imperium_metrics(kernel: Any | None, m: dict[str, Any]) -> None:
    if kernel is None:
        return

    # tasks_submitted — after submit()
    def _after_submit(result: Any, args: tuple, kwargs: dict, exc: Any) -> None:
        m["tasks_submitted"].inc()

    _wrap_sync(kernel, "submit", None, _after_submit)

    # tasks_in_flight / tasks_succeeded / tasks_failed / task_duration_sec
    # — hooked via _run_record
    original_run = getattr(kernel, "_run_record", None)
    if original_run is None:
        return

    @functools.wraps(original_run)
    def _run_record_metrics(rec: Any) -> None:
        m["tasks_in_flight"].inc(1.0)
        t0 = time.time()
        try:
            original_run(rec)
        finally:
            duration = time.time() - t0
            m["tasks_in_flight"].inc(-1.0)
            state = str(getattr(rec, "state", "")).upper()
            if "SUCCEEDED" in state:
                m["tasks_succeeded"].inc()
                m["task_duration_sec"].observe(duration)
            elif "FAILED" in state or "DEAD" in state:
                m["tasks_failed"].inc()
                m["task_duration_sec"].observe(duration)

    kernel._run_record = _run_record_metrics


def _wire_campaign_metrics(engine: Any | None, m: dict[str, Any]) -> None:
    if engine is None:
        return

    # run_campaign is async
    original_run = getattr(engine, "run_campaign", None)
    if original_run is None:
        return

    @functools.wraps(original_run)
    async def _run_campaign_metrics(campaign: Any) -> Any:
        m["campaigns_started"].inc()
        exc: Exception | None = None
        result: Any = None
        try:
            result = await original_run(campaign)
        except Exception as e:  # noqa: BLE001
            exc = e
        status = str(getattr(result, "status", getattr(campaign, "status", "")))
        if "succeed" in status.lower():
            m["campaigns_succeeded"].inc()
        elif "fail" in status.lower() or exc is not None:
            m["campaigns_failed"].inc()
        if exc is not None:
            raise exc
        return result

    engine.run_campaign = _run_campaign_metrics


def _wire_oracle_metrics(planner: Any | None, m: dict[str, Any]) -> None:
    if planner is None:
        return

    original_plan = getattr(planner, "plan", None)
    if original_plan is None:
        return

    @functools.wraps(original_plan)
    async def _plan_metrics(task: Any) -> Any:
        exc: Exception | None = None
        result: Any = None
        try:
            result = await original_plan(task)
        except Exception as e:  # noqa: BLE001
            exc = e
        if exc is not None or (result is not None and not getattr(result, "ok", True)):
            m["oracle_plans_error"].inc()
        else:
            m["oracle_plans_ok"].inc()
        if exc is not None:
            raise exc
        return result

    planner.plan = _plan_metrics
