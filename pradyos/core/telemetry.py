"""Phase 16A — OTel-compatible telemetry pipeline.

Provides:
  TelemetrySpan  — immutable-ish dataclass for a single instrumentation span.
  TelemetryCollector — ring-buffer store with start/finish/record/query API.

Design goals
------------
* OpenTelemetry-compatible field names (span_id, trace_id, parent_id,
  start_ts, end_ts, status, attributes).
* Pure stdlib — no new dependencies.
* Thread-safe via threading.Lock.
* Ring buffer via collections.deque(maxlen=N) — oldest spans auto-evicted.
* Python 3.10 compatible.
"""

from __future__ import annotations

import collections
import threading
import time
import uuid
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_id() -> str:
    """Return a fresh UUID4 as a compact hex string (32 chars, no hyphens)."""
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# TelemetrySpan
# ---------------------------------------------------------------------------


@dataclass
class TelemetrySpan:
    """A single instrumentation span — OTel-compatible field layout.

    Parameters
    ----------
    name:       Human-readable operation name, e.g. ``"campaign.run"``.
    service:    Logical service that emitted this span, e.g. ``"sovereign"``.
    trace_id:   Hex UUID that groups related spans into a trace.
    start_ts:   Unix timestamp (float) when the span started.
    span_id:    Unique hex UUID for this span; auto-generated if falsy.
    parent_id:  ``span_id`` of the parent span, or ``None`` for root spans.
    end_ts:     Unix timestamp when the span finished; ``None`` while running.
    status:     ``"ok"`` | ``"error"`` | ``"running"``.
    attributes: Arbitrary key/value metadata dict.
    """

    name: str
    service: str
    trace_id: str
    start_ts: float
    span_id: str = field(default_factory=_new_id)
    parent_id: str | None = None
    end_ts: float | None = None
    status: str = "running"
    attributes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Ensure span_id is always populated (handles span_id="" edge-case)
        if not self.span_id:
            self.span_id = _new_id()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def duration_ms(self) -> float | None:
        """Return elapsed milliseconds, or ``None`` if span is still running."""
        if self.end_ts is None:
            return None
        return (self.end_ts - self.start_ts) * 1000.0

    def to_dict(self) -> dict:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "service": self.service,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "status": self.status,
            "attributes": dict(self.attributes),
            "duration_ms": self.duration_ms(),
        }


# ---------------------------------------------------------------------------
# TelemetryCollector
# ---------------------------------------------------------------------------


class TelemetryCollector:
    """Ring-buffer telemetry store.

    Parameters
    ----------
    maxlen: Maximum number of spans retained.  Oldest are evicted first.
    """

    def __init__(self, maxlen: int = 500) -> None:
        self._spans: collections.deque = collections.deque(maxlen=maxlen)
        # Index: span_id -> span (for O(1) finish_span lookup)
        self._index: dict = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Span lifecycle
    # ------------------------------------------------------------------

    def start_span(
        self,
        name: str,
        service: str,
        trace_id: str | None = None,
        parent_id: str | None = None,
        attributes: dict | None = None,
    ) -> TelemetrySpan:
        """Create a new span in ``"running"`` state and append it to the buffer.

        Returns the new :class:`TelemetrySpan`.
        """
        span = TelemetrySpan(
            name=name,
            service=service,
            trace_id=trace_id if trace_id else _new_id(),
            start_ts=time.time(),
            parent_id=parent_id,
            status="running",
            attributes=dict(attributes) if attributes else {},
        )
        with self._lock:
            # If the deque is full, remove the oldest entry from the index.
            if len(self._spans) == self._spans.maxlen and self._spans:
                oldest = self._spans[0]
                self._index.pop(oldest.span_id, None)
            self._spans.append(span)
            self._index[span.span_id] = span
        return span

    def finish_span(
        self,
        span_id: str,
        status: str = "ok",
        attributes: dict | None = None,
    ) -> TelemetrySpan | None:
        """Finalise a span by ``span_id``.

        Sets ``end_ts``, ``status``, and merges any extra ``attributes``.
        Returns the updated span, or ``None`` if the span_id is not found.
        """
        with self._lock:
            span = self._index.get(span_id)
            if span is None:
                return None
            span.end_ts = time.time()
            span.status = status
            if attributes:
                span.attributes.update(attributes)
        return span

    def record(
        self,
        name: str,
        service: str,
        status: str = "ok",
        duration_ms: float | None = None,
        trace_id: str | None = None,
        attributes: dict | None = None,
    ) -> TelemetrySpan:
        """One-shot span — creates and immediately finishes a span.

        If *duration_ms* is provided, ``end_ts = start_ts + duration_ms/1000``.
        Otherwise ``end_ts = start_ts`` (zero-duration instant event).
        """
        span = TelemetrySpan(
            name=name,
            service=service,
            trace_id=trace_id if trace_id else _new_id(),
            start_ts=time.time(),
            status=status,
            attributes=dict(attributes) if attributes else {},
        )
        if duration_ms is not None:
            span.end_ts = span.start_ts + duration_ms / 1000.0
        else:
            span.end_ts = span.start_ts
        with self._lock:
            if len(self._spans) == self._spans.maxlen and self._spans:
                oldest = self._spans[0]
                self._index.pop(oldest.span_id, None)
            self._spans.append(span)
            self._index[span.span_id] = span
        return span

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_spans(
        self,
        limit: int = 100,
        service: str | None = None,
        status: str | None = None,
    ) -> list:
        """Return the most-recent spans first, with optional filters.

        Parameters
        ----------
        limit:   Maximum number of results returned.
        service: If given, only include spans whose ``service`` matches.
        status:  If given, only include spans whose ``status`` matches.
        """
        with self._lock:
            results = []
            for span in reversed(self._spans):
                if service is not None and span.service != service:
                    continue
                if status is not None and span.status != status:
                    continue
                results.append(span)
                if len(results) >= limit:
                    break
        return results

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all spans from the buffer and the index."""
        with self._lock:
            self._spans.clear()
            self._index.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._spans)
