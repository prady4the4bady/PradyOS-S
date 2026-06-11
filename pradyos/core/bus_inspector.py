"""Phase 27: Sovereign Event Bus Inspector — live diagnostic ring buffer."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class BusEvent:
    """A single recorded event on the bus."""

    topic: str
    payload: dict
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


class BusInspector:
    """Thread-safe ring-buffer diagnostic inspector for all event-bus messages."""

    def __init__(self, max_size: int = 500) -> None:
        self._max_size = max_size
        self._buffer: deque[BusEvent] = deque(maxlen=max_size)
        self._topic_counts: dict[str, int] = {}
        self._total_events: int = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        topic: str,
        payload: dict | None = None,
        timestamp: float | None = None,
    ) -> BusEvent:
        """Record a bus event and return the created BusEvent."""
        if payload is None:
            payload = {}
        if timestamp is None:
            timestamp = time.time()

        event = BusEvent(topic=topic, payload=payload, timestamp=timestamp)
        with self._lock:
            self._buffer.append(event)
            self._topic_counts[topic] = self._topic_counts.get(topic, 0) + 1
            self._total_events += 1
        return event

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_events(
        self,
        topic: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[BusEvent]:
        """Return events from the ring buffer (oldest-first).

        Args:
            topic:  If given, filter to events with this topic only.
            limit:  Maximum number of events to return (after offset).
            offset: Number of events to skip from the start (after filtering).

        Returns:
            List of BusEvent, oldest first.
        """
        with self._lock:
            events: list[BusEvent] = list(self._buffer)

        if topic is not None:
            events = [e for e in events if e.topic == topic]

        events = events[offset:]
        if limit is not None:
            events = events[:limit]

        return events

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return diagnostic statistics for the inspector."""
        with self._lock:
            return {
                "total_events": self._total_events,
                "buffer_size": len(self._buffer),
                "max_size": self._max_size,
                "topics": dict(self._topic_counts),
            }

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear the ring buffer and reset all per-topic counters."""
        with self._lock:
            self._buffer.clear()
            self._topic_counts.clear()
            self._total_events = 0
