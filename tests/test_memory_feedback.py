"""Tests for Memory Feedback Loop (Phase 4B).

All tests are self-contained — no live Ollama, no live filesystem.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from pradyos.core.bus import EventBus
from pradyos.memory_feedback import MemoryFeedbackHook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_oracle(memory: Any | None = None) -> MagicMock:
    """Return a mock Oracle with an async record_outcome method."""
    oracle = MagicMock()
    outcomes: list[dict] = []

    async def _record(task_id: str, intent: str, outcome: str, plan: Any = None) -> None:
        outcomes.append(
            {
                "task_id": task_id,
                "intent": intent,
                "outcome": outcome,
                "plan": plan,
            }
        )
        if memory is not None:
            memory.store("oracle", {"task_id": task_id, "outcome": outcome})

    oracle.record_outcome = _record
    oracle._outcomes = outcomes
    return oracle


def _wait_for_outcome(oracle: Any, timeout: float = 2.0) -> bool:
    """Spin-wait until at least one outcome is recorded."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if oracle._outcomes:
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------------------
# 1. attach() registers the hook — no double-attach
# ---------------------------------------------------------------------------


def test_attach_registers_once() -> None:
    bus = EventBus()
    oracle = _make_oracle()
    hook = MemoryFeedbackHook()

    hook.attach(bus, oracle)
    hook.attach(bus, oracle)  # should be a no-op

    # Publish one event; expect exactly one record_outcome call
    bus.publish("campaign.succeeded", {
        "campaign_id": "camp-1",
        "name": "test",
        "intent": "do a thing",
        "status": "succeeded",
        "progress": {"succeeded": 2},
    })

    assert _wait_for_outcome(oracle), "record_outcome not called within timeout"
    assert len(oracle._outcomes) == 1


# ---------------------------------------------------------------------------
# 2. campaign.succeeded → outcome == "success"
# ---------------------------------------------------------------------------


def test_success_outcome_stored() -> None:
    bus = EventBus()
    oracle = _make_oracle()
    hook = MemoryFeedbackHook()
    hook.attach(bus, oracle)

    bus.publish("campaign.succeeded", {
        "campaign_id": "camp-s1",
        "name": "Deploy feature",
        "intent": "deploy the new auth module",
        "status": "succeeded",
        "progress": {"succeeded": 3},
    })

    assert _wait_for_outcome(oracle)
    out = oracle._outcomes[0]
    assert out["outcome"] == "success"
    assert out["task_id"] == "camp-s1"
    assert "deploy the new auth module" in out["intent"]


# ---------------------------------------------------------------------------
# 3. campaign.failed → outcome contains "failure"
# ---------------------------------------------------------------------------


def test_failure_outcome_stored() -> None:
    bus = EventBus()
    oracle = _make_oracle()
    hook = MemoryFeedbackHook()
    hook.attach(bus, oracle)

    bus.publish("campaign.failed", {
        "campaign_id": "camp-f1",
        "name": "Risky Op",
        "intent": "upgrade kernel",
        "status": "failed",
        "error": "permission denied",
        "progress": {"failed": 1},
    })

    assert _wait_for_outcome(oracle)
    out = oracle._outcomes[0]
    assert "failure" in out["outcome"]
    assert out["task_id"] == "camp-f1"


# ---------------------------------------------------------------------------
# 4. Both events independently trigger recording
# ---------------------------------------------------------------------------


def test_both_terminal_events_trigger_recording() -> None:
    bus = EventBus()
    oracle = _make_oracle()
    hook = MemoryFeedbackHook()
    hook.attach(bus, oracle)

    bus.publish("campaign.succeeded", {
        "campaign_id": "camp-both-1",
        "name": "First",
        "intent": "first campaign",
        "status": "succeeded",
        "progress": {},
    })
    bus.publish("campaign.failed", {
        "campaign_id": "camp-both-2",
        "name": "Second",
        "intent": "second campaign",
        "status": "failed",
        "error": None,
        "progress": {},
    })

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if len(oracle._outcomes) >= 2:
            break
        time.sleep(0.02)

    assert len(oracle._outcomes) >= 2
    outcomes_text = {o["outcome"] for o in oracle._outcomes}
    assert "success" in outcomes_text
    assert any("failure" in o for o in outcomes_text)


# ---------------------------------------------------------------------------
# 5. Outcome stored in Memory Citadel after campaign.succeeded
# ---------------------------------------------------------------------------


def test_outcome_stored_in_memory_citadel() -> None:
    from pradyos.memory_citadel.inmem import InMemoryCitadel

    citadel = InMemoryCitadel()
    oracle = _make_oracle(memory=citadel)
    bus = EventBus()
    hook = MemoryFeedbackHook()
    hook.attach(bus, oracle)

    bus.publish("campaign.succeeded", {
        "campaign_id": "camp-cit",
        "name": "Citadel Test",
        "intent": "store in memory",
        "status": "succeeded",
        "progress": {"succeeded": 1},
    })

    assert _wait_for_outcome(oracle)
    records = citadel._store.get("oracle", [])
    assert any(r.get("task_id") == "camp-cit" for r in records), (
        f"camp-cit not found in citadel; stored={records}"
    )


# ---------------------------------------------------------------------------
# 6. Outcome stored in Memory Citadel after campaign.failed
# ---------------------------------------------------------------------------


def test_failure_stored_in_memory_citadel() -> None:
    from pradyos.memory_citadel.inmem import InMemoryCitadel

    citadel = InMemoryCitadel()
    oracle = _make_oracle(memory=citadel)
    bus = EventBus()
    hook = MemoryFeedbackHook()
    hook.attach(bus, oracle)

    bus.publish("campaign.failed", {
        "campaign_id": "camp-cit-fail",
        "name": "Fail Test",
        "intent": "fail store",
        "status": "failed",
        "error": "boom",
        "progress": {},
    })

    assert _wait_for_outcome(oracle)
    records = citadel._store.get("oracle", [])
    assert any(r.get("task_id") == "camp-cit-fail" for r in records)


# ---------------------------------------------------------------------------
# 7. detach() stops event processing
# ---------------------------------------------------------------------------


def test_detach_stops_processing() -> None:
    bus = EventBus()
    oracle = _make_oracle()
    hook = MemoryFeedbackHook()
    hook.attach(bus, oracle)
    hook.detach()

    bus.publish("campaign.succeeded", {
        "campaign_id": "camp-det",
        "name": "After detach",
        "intent": "should not record",
        "status": "succeeded",
        "progress": {},
    })

    time.sleep(0.1)  # give background thread time if it mistakenly ran
    assert len(oracle._outcomes) == 0, "Hook recorded after detach"


# ---------------------------------------------------------------------------
# 8. Non-terminal events are ignored
# ---------------------------------------------------------------------------


def test_non_terminal_events_ignored() -> None:
    bus = EventBus()
    oracle = _make_oracle()
    hook = MemoryFeedbackHook()
    hook.attach(bus, oracle)

    bus.publish("campaign.created", {"campaign_id": "camp-c", "name": "x"})
    bus.publish("campaign.node.running", {"campaign_id": "camp-c", "node_id": "n1"})
    bus.publish("campaign.node.succeeded", {"campaign_id": "camp-c", "node_id": "n1"})

    time.sleep(0.1)
    assert len(oracle._outcomes) == 0
