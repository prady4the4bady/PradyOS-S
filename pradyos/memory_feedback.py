"""Memory Feedback Loop (Phase 4B).

After every campaign terminal event (``campaign.succeeded`` /
``campaign.failed``), ``MemoryFeedbackHook`` automatically calls
``Oracle.record_outcome()`` so ORACLE learns from each campaign result.

Design
------
* Hook is registered **once** at IMPERIUM startup via
  ``MemoryFeedbackHook.attach(bus, oracle)``.
* No manual wiring required per campaign.
* Both success and failure paths are covered; error in recording is
  logged and swallowed so it never blocks the event loop.
* ``record_outcome`` is called asynchronously in a background thread to
  avoid blocking the EventBus dispatch thread.

Windows safety
--------------
* No ``AF_UNIX``, no ``fork()``, no ``os.killpg()``
* Standard ``threading`` for async dispatch
* All paths via ``pathlib.Path``
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

log = logging.getLogger("pradyos.memory_feedback")

_TERMINAL_TOPICS = ("campaign.succeeded", "campaign.failed")


class MemoryFeedbackHook:
    """Subscribes to campaign terminal events and persists outcomes to Memory Citadel.

    Usage::

        oracle = Oracle(memory_store=citadel)
        hook = MemoryFeedbackHook()
        hook.attach(bus, oracle)
        # From this point on, every campaign.succeeded / campaign.failed
        # event triggers Oracle.record_outcome() automatically.
    """

    def __init__(self) -> None:
        self._oracle: Any = None
        self._bus: Any = None
        self._attached = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def attach(self, bus: Any, oracle: Any) -> None:
        """Register campaign terminal event subscribers.

        Parameters
        ----------
        bus:
            An EventBus instance (``pradyos.core.bus.EventBus``).
        oracle:
            An Oracle (or compatible object) with an async
            ``record_outcome(task_id, intent, outcome, plan)`` method.
        """
        if self._attached:
            log.debug("MemoryFeedbackHook already attached — skipping")
            return

        self._oracle = oracle
        self._bus = bus

        for topic in _TERMINAL_TOPICS:
            bus.subscribe(topic, self._on_terminal)

        self._attached = True
        log.info("MemoryFeedbackHook attached to bus (%s)", ", ".join(_TERMINAL_TOPICS))

    def detach(self) -> None:
        """Unsubscribe from all terminal topics (useful in tests)."""
        if not self._attached or self._bus is None:
            return
        for topic in _TERMINAL_TOPICS:
            try:
                self._bus.unsubscribe(topic, self._on_terminal)
            except Exception:  # noqa: BLE001
                pass
        self._attached = False
        log.debug("MemoryFeedbackHook detached")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_terminal(self, topic: str, payload: dict[str, Any]) -> None:
        """Called on campaign.succeeded or campaign.failed."""
        campaign_id = payload.get("campaign_id", "unknown")
        campaign_name = payload.get("name", "")
        intent = payload.get("intent", campaign_name)
        status = payload.get("status", topic.split(".")[-1])
        error = payload.get("error")
        progress = payload.get("progress", {})

        outcome = "success" if topic == "campaign.succeeded" else "failure"
        if error:
            outcome = f"failure: {error}"

        log.info(
            "MemoryFeedbackHook: recording outcome for campaign %s → %s",
            campaign_id,
            outcome,
        )

        # Build a summary record that ORACLE / Memory Citadel understands
        record = {
            "task_id": campaign_id,
            "summary": intent or campaign_name,
            "outcome": outcome,
            "step_count": sum(progress.values()) if progress else 0,
            "required_approval": False,
            "campaign_name": campaign_name,
            "campaign_status": status,
            "recorded_at": time.time(),
        }

        # Fire-and-forget in a background thread so we never block the bus
        thread = threading.Thread(
            target=self._record_sync,
            args=(record,),
            name=f"mem-feedback-{campaign_id[:8]}",
            daemon=True,
        )
        thread.start()

    def _record_sync(self, record: dict[str, Any]) -> None:
        """Synchronously call Oracle.record_outcome() (runs in background thread)."""
        if self._oracle is None:
            return
        try:
            # Build a minimal OraclePlan-compatible stub from record data
            plan_stub = _MinimalPlan(step_count=record.get("step_count", 0))
            coro = self._oracle.record_outcome(
                task_id=record["task_id"],
                intent=record["summary"],
                outcome=record["outcome"],
                plan=plan_stub,
            )
            if asyncio.iscoroutine(coro):
                # Run async record_outcome in a fresh event loop on this thread
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(coro)
                finally:
                    loop.close()
        except Exception as e:  # noqa: BLE001
            log.debug("MemoryFeedbackHook record_outcome failed (non-fatal): %s", e)


class _MinimalPlan:
    """Minimal OraclePlan stub for memory recording purposes."""

    def __init__(self, step_count: int = 0) -> None:
        self.steps = [object()] * step_count  # dummy step objects for len()
        self.requires_approval = False
        self.approval_reason = ""
