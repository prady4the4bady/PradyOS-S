"""Tests for Warden Phase 4 Campaign Guard (Phase 4E).

All tests are self-contained with mocks — no live filesystem, no live processes.
"""

from __future__ import annotations

import asyncio
import time
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pradyos.core.bus import EventBus
from pradyos.warden_phase4 import WardenCampaignGuard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(rollback_result: dict | None = None, async_rollback: bool = True) -> MagicMock:
    """Return a mock CampaignEngine with a rollback_campaign method."""
    engine = MagicMock()
    calls: list[str] = []
    result = rollback_result or {"ok": True}

    if async_rollback:
        async def _rollback(campaign_id: str) -> dict:
            calls.append(campaign_id)
            return result

        engine.rollback_campaign = _rollback
    else:
        def _rollback_sync(campaign_id: str) -> dict:
            calls.append(campaign_id)
            return result

        engine.rollback_campaign = _rollback_sync

    engine._rollback_calls = calls
    return engine


def _publish_node_failures(bus: EventBus, campaign_id: str, count: int) -> None:
    """Publish *count* campaign.node.failed events for the given campaign."""
    for i in range(count):
        bus.publish("campaign.node.failed", {
            "campaign_id": campaign_id,
            "node_id": f"node-{i}",
            "intent": f"failing step {i}",
            "error": "simulated failure",
        })


def _wait_for_rollback(engine: Any, campaign_id: str, timeout: float = 2.0) -> bool:
    """Spin-wait until rollback is called for the campaign."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if campaign_id in engine._rollback_calls:
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------------------
# 1. attach() registers — guard active after attach
# ---------------------------------------------------------------------------


def test_attach_registers_on_bus() -> None:
    bus = EventBus()
    engine = _make_engine()
    guard = WardenCampaignGuard(threshold=3, window_sec=60)
    guard.attach(bus, engine)
    assert guard._attached is True


# ---------------------------------------------------------------------------
# 2. Rollback triggered after threshold failures
# ---------------------------------------------------------------------------


def test_rollback_triggered_at_threshold() -> None:
    bus = EventBus()
    engine = _make_engine()
    guard = WardenCampaignGuard(threshold=3, window_sec=60)
    guard.attach(bus, engine)

    _publish_node_failures(bus, "camp-thresh", 3)

    assert _wait_for_rollback(engine, "camp-thresh"), "Rollback not triggered at threshold"
    assert guard.rollback_was_triggered("camp-thresh")


# ---------------------------------------------------------------------------
# 3. Rollback NOT triggered below threshold
# ---------------------------------------------------------------------------


def test_no_rollback_below_threshold() -> None:
    bus = EventBus()
    engine = _make_engine()
    guard = WardenCampaignGuard(threshold=3, window_sec=60)
    guard.attach(bus, engine)

    _publish_node_failures(bus, "camp-below", 2)

    time.sleep(0.1)  # Give background thread time if it mistakenly fired
    assert engine._rollback_calls == [], "Rollback should NOT be called below threshold"
    assert not guard.rollback_was_triggered("camp-below")


# ---------------------------------------------------------------------------
# 4. Rollback triggered only once (not on every subsequent failure)
# ---------------------------------------------------------------------------


def test_rollback_triggered_only_once() -> None:
    bus = EventBus()
    engine = _make_engine()
    guard = WardenCampaignGuard(threshold=2, window_sec=60)
    guard.attach(bus, engine)

    _publish_node_failures(bus, "camp-once", 5)

    _wait_for_rollback(engine, "camp-once", timeout=2.0)
    time.sleep(0.1)  # Extra wait for any additional spurious calls

    assert engine._rollback_calls.count("camp-once") == 1, (
        f"Rollback called {engine._rollback_calls.count('camp-once')} times, expected 1"
    )


# ---------------------------------------------------------------------------
# 5. Different campaigns are tracked independently
# ---------------------------------------------------------------------------


def test_independent_campaign_tracking() -> None:
    bus = EventBus()
    engine = _make_engine()
    guard = WardenCampaignGuard(threshold=3, window_sec=60)
    guard.attach(bus, engine)

    # camp-A: 2 failures (below threshold)
    _publish_node_failures(bus, "camp-a", 2)
    # camp-B: 3 failures (at threshold)
    _publish_node_failures(bus, "camp-b", 3)

    assert _wait_for_rollback(engine, "camp-b"), "camp-b should trigger rollback"
    time.sleep(0.1)
    assert "camp-a" not in engine._rollback_calls, "camp-a should NOT rollback"


# ---------------------------------------------------------------------------
# 6. Env var WARDEN_CAMPAIGN_FAIL_THRESHOLD overrides default
# ---------------------------------------------------------------------------


def test_env_threshold_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WARDEN_CAMPAIGN_FAIL_THRESHOLD", "2")
    monkeypatch.setenv("WARDEN_CAMPAIGN_FAIL_WINDOW_S", "60")

    bus = EventBus()
    engine = _make_engine()
    guard = WardenCampaignGuard()  # reads from env
    guard.attach(bus, engine)

    assert guard.threshold == 2

    _publish_node_failures(bus, "camp-env", 2)
    assert _wait_for_rollback(engine, "camp-env"), "Should rollback at env-set threshold of 2"


# ---------------------------------------------------------------------------
# 7. Env var WARDEN_CAMPAIGN_FAIL_WINDOW_S configures window
# ---------------------------------------------------------------------------


def test_env_window_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WARDEN_CAMPAIGN_FAIL_THRESHOLD", "3")
    monkeypatch.setenv("WARDEN_CAMPAIGN_FAIL_WINDOW_S", "30")

    guard = WardenCampaignGuard()  # reads from env
    assert guard.window_sec == 30.0


# ---------------------------------------------------------------------------
# 8. failure_count() returns correct rolling count
# ---------------------------------------------------------------------------


def test_failure_count_helper() -> None:
    bus = EventBus()
    engine = _make_engine()
    guard = WardenCampaignGuard(threshold=10, window_sec=60)  # high threshold to avoid rollback
    guard.attach(bus, engine)

    _publish_node_failures(bus, "camp-cnt", 4)
    assert guard.failure_count("camp-cnt") == 4


# ---------------------------------------------------------------------------
# 9. Failures outside window don't count
# ---------------------------------------------------------------------------


def test_old_failures_outside_window_dont_count() -> None:
    bus = EventBus()
    engine = _make_engine()
    guard = WardenCampaignGuard(threshold=3, window_sec=0.05)  # 50ms window
    guard.attach(bus, engine)

    # Publish 2 failures
    _publish_node_failures(bus, "camp-win", 2)
    # Wait for window to expire
    time.sleep(0.1)
    # Publish 1 more — total recent should be 1 (below threshold)
    _publish_node_failures(bus, "camp-win", 1)

    time.sleep(0.05)
    assert not guard.rollback_was_triggered("camp-win"), (
        "Old failures outside window should not contribute to threshold"
    )


# ---------------------------------------------------------------------------
# 10. Sync rollback engine is also supported
# ---------------------------------------------------------------------------


def test_sync_rollback_engine() -> None:
    bus = EventBus()
    engine = _make_engine(async_rollback=False)
    guard = WardenCampaignGuard(threshold=3, window_sec=60)
    guard.attach(bus, engine)

    _publish_node_failures(bus, "camp-sync", 3)
    assert _wait_for_rollback(engine, "camp-sync"), "Sync rollback not triggered"


# ---------------------------------------------------------------------------
# 11. detach() stops event processing
# ---------------------------------------------------------------------------


def test_detach_stops_guard() -> None:
    bus = EventBus()
    engine = _make_engine()
    guard = WardenCampaignGuard(threshold=2, window_sec=60)
    guard.attach(bus, engine)
    guard.detach()

    _publish_node_failures(bus, "camp-det", 3)
    time.sleep(0.1)
    assert engine._rollback_calls == [], "Guard should not trigger after detach"
