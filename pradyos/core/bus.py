"""Lightweight in-process pub/sub bus.

Lets the planes wire to each other without compiled-in coupling. IMPERIUM
publishes ``task.completed``; AURORA THRONE subscribes. WARDEN GRID
publishes ``incident.raised``; IMPERIUM subscribes and may dispatch a
TITAN OPS repair lane.

For Phase 0 this is in-process only. Phase 3+ may swap in NATS / a real
broker without changing call sites.
"""

from __future__ import annotations

import os
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

Subscriber = Callable[[str, dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, topic: str, fn: Subscriber) -> None:
        with self._lock:
            self._subs[topic].append(fn)

    def unsubscribe(self, topic: str, fn: Subscriber) -> None:
        with self._lock:
            if fn in self._subs.get(topic, []):
                self._subs[topic].remove(fn)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        with self._lock:
            targets = list(self._subs.get(topic, []))
            wildcard = list(self._subs.get("*", []))
        for fn in targets + wildcard:
            try:
                fn(topic, payload)
            except Exception:  # noqa: BLE001 -- subscriber faults are isolated
                pass


_singleton: EventBus | None = None
_lock = threading.Lock()


def get_bus() -> EventBus:  # type: ignore[return-value]
    """Return the process-global bus singleton.

    When PRADYOS_BUS_BACKEND=redis is set, returns a RedisBus
    (cross-process, Redis-backed).  Otherwise returns the lightweight
    in-process EventBus.  All call sites are unaffected -- both
    classes expose the identical subscribe / unsubscribe / publish API.
    """
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                backend = os.environ.get("PRADYOS_BUS_BACKEND", "").lower()
                if backend == "redis":
                    from pradyos.core.redis_bus import RedisBus  # noqa: PLC0415

                    _singleton = RedisBus()  # type: ignore[assignment]
                else:
                    _singleton = EventBus()
    return _singleton  # type: ignore[return-value]


def reset_bus_for_tests() -> EventBus:
    """Reset the global singleton and return a fresh EventBus.

    Called by the ``isolated_bus`` pytest fixture so every test starts
    with a clean, empty bus and subscribers from previous tests cannot
    bleed through.
    """
    global _singleton
    _singleton = EventBus()
    return _singleton
