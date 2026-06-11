"""AURORA THRONE — CampaignMonitor (Phase 13).

Provides a live window into campaign execution in real time:

  - ``active_campaigns``  — non-terminal campaigns from the registry
  - ``step_timeline``     — last 100 campaign.* bus events (ring buffer)
                            each: {campaign_id, step, status, ts}
  - ``titan_ops_feed``    — last 50 titan.* bus events (ring buffer)
                            each: {topic, payload, ts}

Usage
-----
    from pradyos.aurora_throne.campaign_monitor import CampaignMonitor

    monitor = CampaignMonitor(bus=bus, campaign_registry=registry)
    monitor.start()                     # subscribe to bus
    snap = monitor.get_snapshot()       # CampaignMonitorSnapshot
    monitor.stop()                      # unsubscribe

Ring buffers
------------
  step_timeline  — deque(maxlen=100)  — oldest event evicted on overflow
  titan_ops_feed — deque(maxlen=50)   — oldest event evicted on overflow
"""

from __future__ import annotations

import dataclasses
import time
from collections import deque
from typing import Any

from pradyos.core.bus import EventBus, get_bus

# ---------------------------------------------------------------------------
# CampaignMonitorSnapshot
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class CampaignMonitorSnapshot:
    """Immutable snapshot of live campaign telemetry at a point in time.

    Attributes
    ----------
    active_campaigns:
        List of non-terminal campaigns as dicts (from campaign_registry.active()).
    step_timeline:
        Up to the last 100 campaign.* bus events, each stored as a dict with
        at least: ``campaign_id``, ``step``, ``status``, ``ts`` (float).
    titan_ops_feed:
        Up to the last 50 titan.* bus events, each stored as a dict with
        at least: ``topic``, ``payload``, ``ts`` (float).
    """

    active_campaigns: list
    step_timeline: list
    titan_ops_feed: list

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dictionary representation."""
        return {
            "active_campaigns": self.active_campaigns,
            "step_timeline": self.step_timeline,
            "titan_ops_feed": self.titan_ops_feed,
        }


# ---------------------------------------------------------------------------
# CampaignMonitor
# ---------------------------------------------------------------------------


class CampaignMonitor:
    """Live campaign monitor — injected dependencies, no singletons.

    Subscribes to the process-global EventBus wildcard (``"*"``) and
    routes events to one of two ring buffers based on topic prefix:

      campaign.*  ->  step_timeline   (maxlen=100)
      titan.*     ->  titan_ops_feed  (maxlen=50)

    Parameters
    ----------
    bus:
        :class:`~pradyos.core.bus.EventBus` (or compatible).
        Falls back to the process-global singleton.
    campaign_registry:
        Optional registry exposing an ``active() -> list`` method.
        Falls back to an empty list when not provided.
    """

    AGENT_ID = "aurora_throne.campaign_monitor"
    _BUS_TOPIC = "*"  # wildcard — receive every published event
    _TIMELINE_MAXLEN = 100
    _TITAN_FEED_MAXLEN = 50

    def __init__(
        self,
        bus: Any | None = None,
        campaign_registry: Any | None = None,
    ) -> None:
        self._bus: EventBus = bus or get_bus()
        self._registry: Any = campaign_registry

        # Independent ring buffers
        self._step_timeline: deque = deque(maxlen=self._TIMELINE_MAXLEN)
        self._titan_ops_feed: deque = deque(maxlen=self._TITAN_FEED_MAXLEN)
        self._subscribed: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Subscribe to bus wildcard and begin filling ring buffers."""
        if not self._subscribed:
            self._bus.subscribe(self._BUS_TOPIC, self._on_bus_event)
            self._subscribed = True

    def stop(self) -> None:
        """Unsubscribe from the bus (idempotent)."""
        if self._subscribed:
            self._bus.unsubscribe(self._BUS_TOPIC, self._on_bus_event)
            self._subscribed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_snapshot(self) -> CampaignMonitorSnapshot:
        """Return an immutable snapshot of the current campaign telemetry."""
        return CampaignMonitorSnapshot(
            active_campaigns=self._get_active_campaigns(),
            step_timeline=list(self._step_timeline),
            titan_ops_feed=list(self._titan_ops_feed),
        )

    # ------------------------------------------------------------------
    # Bus subscriber — wildcard handler, routes by topic prefix
    # ------------------------------------------------------------------

    def _on_bus_event(self, topic: str, payload: dict) -> None:
        """EventBus subscriber — routes to the correct ring buffer."""
        if topic.startswith("campaign."):
            self._on_campaign_event(topic, payload)
        elif topic.startswith("titan."):
            self._on_titan_event(topic, payload)

    def _on_campaign_event(self, topic: str, payload: dict) -> None:
        """Append a campaign.* event to the step_timeline ring buffer."""
        ts = time.time()
        self._step_timeline.append(
            {
                "campaign_id": payload.get("campaign_id", ""),
                "step": payload.get("step", topic),
                "status": payload.get("status", ""),
                "ts": ts,
            }
        )

    def _on_titan_event(self, topic: str, payload: dict) -> None:
        """Append a titan.* event to the titan_ops_feed ring buffer."""
        ts = time.time()
        self._titan_ops_feed.append(
            {
                "topic": topic,
                "payload": payload,
                "ts": ts,
            }
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_active_campaigns(self) -> list:
        """Return active campaigns as a list of dicts."""
        if self._registry is None:
            return []
        try:
            campaigns = self._registry.active()
            result = []
            for c in campaigns:
                if hasattr(c, "to_dict"):
                    result.append(c.to_dict())
                elif isinstance(c, dict):
                    result.append(c)
                else:
                    result.append({"id": str(c)})
            return result
        except Exception:  # noqa: BLE001
            return []
