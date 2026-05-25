"""Warden Phase 4 Upgrade — Campaign Failure Guard (Phase 4E).

``WardenCampaignGuard`` subscribes to ``campaign.node.failed`` events on
the EventBus. If a campaign accumulates **≥ threshold** node failures within
a rolling time window, it automatically triggers
``CampaignEngine.rollback_campaign(campaign_id)``.

Configuration (environment variables)
--------------------------------------
``WARDEN_CAMPAIGN_FAIL_THRESHOLD`` (int, default 3)
    Number of ``campaign.node.failed`` events within the window before
    rollback is triggered.
``WARDEN_CAMPAIGN_FAIL_WINDOW_S`` (float, default 60)
    Rolling window in seconds over which failures are counted.

Design notes
------------
* The guard is registered via ``WardenCampaignGuard.attach(bus, engine)``
  which must be called once at IMPERIUM startup.
* Uses ``threading.Lock`` to guard per-campaign failure timestamps
  (EventBus subscribers run on the publishing thread).
* Rollback is dispatched via ``asyncio.run_coroutine_threadsafe`` into a
  dedicated event loop running on a background thread so it never blocks
  the publishing thread.
* If the CampaignEngine is not async, ``engine.rollback_campaign`` is
  called directly in a background thread.

Windows safety
--------------
* All paths via pathlib.Path
* No AF_UNIX, no fork(), no os.killpg()
* Standard asyncio event loop (no uvloop)
* Rollback is threadsafe via threading.Lock + background threads
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections import defaultdict
from typing import Any

log = logging.getLogger("pradyos.warden_phase4")

# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLD = int(os.environ.get("WARDEN_CAMPAIGN_FAIL_THRESHOLD", "3"))
_DEFAULT_WINDOW_S = float(os.environ.get("WARDEN_CAMPAIGN_FAIL_WINDOW_S", "60"))


# ---------------------------------------------------------------------------
# WardenCampaignGuard
# ---------------------------------------------------------------------------


class WardenCampaignGuard:
    """Watches campaign node failures and triggers auto-rollback on breach.

    Parameters
    ----------
    threshold:
        Number of node failures within *window_sec* that trigger rollback.
        Defaults to ``WARDEN_CAMPAIGN_FAIL_THRESHOLD`` env var (default 3).
    window_sec:
        Rolling window in seconds. Defaults to ``WARDEN_CAMPAIGN_FAIL_WINDOW_S``
        env var (default 60).
    """

    def __init__(
        self,
        threshold: int | None = None,
        window_sec: float | None = None,
    ) -> None:
        self.threshold = (
            threshold
            if threshold is not None
            else int(os.environ.get("WARDEN_CAMPAIGN_FAIL_THRESHOLD", str(_DEFAULT_THRESHOLD)))
        )
        self.window_sec = (
            window_sec
            if window_sec is not None
            else float(os.environ.get("WARDEN_CAMPAIGN_FAIL_WINDOW_S", str(_DEFAULT_WINDOW_S)))
        )

        # Per-campaign: list of failure timestamps (protected by _lock)
        self._fail_times: dict[str, list[float]] = defaultdict(list)
        self._rollback_triggered: set[str] = set()
        self._lock = threading.Lock()
        self._engine: Any = None
        self._bus: Any = None
        self._attached = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def attach(self, bus: Any, engine: Any) -> None:
        """Register on the EventBus and wire to the CampaignEngine.

        Parameters
        ----------
        bus:
            EventBus instance.
        engine:
            CampaignEngine (or compatible object) with an async
            ``rollback_campaign(campaign_id)`` method.
        """
        if self._attached:
            log.debug("WardenCampaignGuard already attached — skipping")
            return

        self._bus = bus
        self._engine = engine
        bus.subscribe("campaign.node.failed", self._on_node_failed)
        bus.subscribe("campaign.*", self._on_campaign_event)
        self._attached = True

        log.info(
            "WardenCampaignGuard attached (threshold=%d, window=%.0fs)",
            self.threshold,
            self.window_sec,
        )

    def detach(self) -> None:
        """Unsubscribe from all events (useful in tests)."""
        if not self._attached or self._bus is None:
            return
        try:
            self._bus.unsubscribe("campaign.node.failed", self._on_node_failed)
            self._bus.unsubscribe("campaign.*", self._on_campaign_event)
        except Exception:  # noqa: BLE001
            pass
        self._attached = False

    # ------------------------------------------------------------------
    # Internal event handlers
    # ------------------------------------------------------------------

    def _on_node_failed(self, topic: str, payload: dict[str, Any]) -> None:
        """Handle campaign.node.failed events."""
        campaign_id = payload.get("campaign_id")
        if not campaign_id:
            return

        now = time.monotonic()

        with self._lock:
            # Skip if rollback already triggered for this campaign
            if campaign_id in self._rollback_triggered:
                return

            # Append this failure timestamp
            times = self._fail_times[campaign_id]
            times.append(now)

            # Prune timestamps outside the rolling window
            cutoff = now - self.window_sec
            times[:] = [t for t in times if t >= cutoff]
            recent_count = len(times)

        log.debug(
            "WardenCampaignGuard: campaign=%s recent_failures=%d threshold=%d",
            campaign_id,
            recent_count,
            self.threshold,
        )

        if recent_count >= self.threshold:
            with self._lock:
                if campaign_id in self._rollback_triggered:
                    return  # another thread already triggered
                self._rollback_triggered.add(campaign_id)

            log.warning(
                "WardenCampaignGuard: threshold breached for campaign %s "
                "(%d failures in %.0fs) — triggering rollback",
                campaign_id,
                recent_count,
                self.window_sec,
            )
            self._trigger_rollback(campaign_id)

    def _on_campaign_event(self, topic: str, payload: dict[str, Any]) -> None:
        """Clear failure tracking when a campaign reaches a terminal state."""
        terminal_topics = {
            "campaign.succeeded",
            "campaign.failed",
            "campaign.rolled_back",
            "campaign.cancelled",
        }
        if topic not in terminal_topics:
            return
        campaign_id = payload.get("campaign_id")
        if not campaign_id:
            return
        with self._lock:
            self._fail_times.pop(campaign_id, None)

    def _trigger_rollback(self, campaign_id: str) -> None:
        """Dispatch rollback in a background thread."""
        if self._engine is None:
            log.warning("WardenCampaignGuard: no engine attached; cannot rollback %s", campaign_id)
            return

        thread = threading.Thread(
            target=self._do_rollback,
            args=(campaign_id,),
            name=f"warden-rollback-{campaign_id[:8]}",
            daemon=True,
        )
        thread.start()

    def _do_rollback(self, campaign_id: str) -> None:
        """Execute rollback synchronously in a background thread."""
        if self._engine is None:
            return
        try:
            rollback_fn = self._engine.rollback_campaign
            # Try async first
            import inspect
            if inspect.iscoroutinefunction(rollback_fn):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(rollback_fn(campaign_id))
                finally:
                    loop.close()
            else:
                result = rollback_fn(campaign_id)

            log.info(
                "WardenCampaignGuard: rollback complete for campaign %s → %s",
                campaign_id,
                result,
            )
        except Exception as e:  # noqa: BLE001
            log.error(
                "WardenCampaignGuard: rollback error for campaign %s: %s",
                campaign_id,
                e,
            )

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def failure_count(self, campaign_id: str) -> int:
        """Return the current rolling failure count for a campaign."""
        now = time.monotonic()
        cutoff = now - self.window_sec
        with self._lock:
            times = self._fail_times.get(campaign_id, [])
            return sum(1 for t in times if t >= cutoff)

    def rollback_was_triggered(self, campaign_id: str) -> bool:
        """Return True if rollback was triggered for this campaign."""
        with self._lock:
            return campaign_id in self._rollback_triggered
