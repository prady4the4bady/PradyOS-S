"""Sovereign Audit Replay Engine (Phase 25).

Time-travel state reconstructor that replays the audit ledger up to any
requested timestamp, returning a deterministic snapshot of reconstructed state.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ReplayEntry:
    """A single ledger event captured for replay."""

    timestamp: float
    event_type: str
    payload: dict

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "payload": self.payload,
        }


@dataclass
class ReplaySnapshot:
    """Reconstructed system state at a given point in time."""

    at: float
    entries: list
    state: dict
    event_count: int

    def to_dict(self) -> dict:
        return {
            "at": self.at,
            "entries": [e.to_dict() for e in self.entries],
            "state": self.state,
            "event_count": self.event_count,
        }


class AuditReplayEngine:
    """Replays the audit ledger to reconstruct state at any point in time.

    Parameters
    ----------
    ledger:
        Any object with an ``entries`` property that returns a list of dicts.
        Each dict must have at minimum ``"timestamp"`` (float) and
        ``"event_type"`` (str); ``"payload"`` (dict) is optional.
        When *None*, the engine operates in standalone mode and uses its own
        internal list populated via :meth:`add_entry`.
    """

    def __init__(self, ledger: Any | None = None) -> None:
        self._ledger = ledger
        self._internal: list = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replay(self, at: float) -> ReplaySnapshot:
        """Replay all ledger entries up to and including *at*.

        Parameters
        ----------
        at:
            Unix timestamp ceiling.  Entries whose ``timestamp`` is <= *at*
            are included; later entries are excluded.

        Returns
        -------
        ReplaySnapshot
            Reconstructed snapshot.  If no ledger is attached and the
            internal list is empty, returns an empty snapshot.
        """
        raw: list = self._source_entries()

        # Filter <= at
        filtered = [e for e in raw if e.get("timestamp", 0.0) <= at]

        # Sort ascending by timestamp
        filtered.sort(key=lambda e: e.get("timestamp", 0.0))

        # Reconstruct state via shallow merge
        state: dict = {}
        for entry in filtered:
            payload = entry.get("payload") or {}
            state.update(payload)

        entries = [
            ReplayEntry(
                timestamp=e["timestamp"],
                event_type=e["event_type"],
                payload=e.get("payload") or {},
            )
            for e in filtered
        ]

        return ReplaySnapshot(
            at=at,
            entries=entries,
            state=state,
            event_count=len(filtered),
        )

    def add_entry(
        self,
        event_type: str,
        payload: dict,
        timestamp: float | None = None,
    ) -> ReplayEntry:
        """Add an entry to the internal list (used when no ledger is provided).

        Parameters
        ----------
        event_type:
            Short string categorising the event.
        payload:
            Arbitrary dict merged into state during replay.
        timestamp:
            Unix timestamp; defaults to :func:`time.time`.

        Returns
        -------
        ReplayEntry
            The newly created entry.
        """
        ts = timestamp if timestamp is not None else time.time()
        entry = ReplayEntry(timestamp=ts, event_type=event_type, payload=payload)
        with self._lock:
            self._internal.append(
                {"timestamp": ts, "event_type": event_type, "payload": payload}
            )
        return entry

    def clear(self) -> None:
        """Remove all internally added entries."""
        with self._lock:
            self._internal.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _source_entries(self) -> list:
        """Return the raw entry list from the ledger or internal store."""
        if self._ledger is not None:
            try:
                return list(self._ledger.entries)
            except Exception:
                return []
        with self._lock:
            return list(self._internal)
