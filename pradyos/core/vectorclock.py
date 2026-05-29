"""Phase 75 — Sovereign Vector Clock (distributed causality tracker).

A vector clock captures the *causal* ordering of events across independent
actors (nodes, services, replicas). Each actor keeps a counter; an actor bumps
its own counter on a local event (:meth:`tick`), and folds in another clock's
knowledge when it receives a message (:meth:`merge`, element-wise max). Comparing
two clocks (:meth:`compare`) then answers the only question that matters in a
distributed system: did A happen *before* B, *after* B, are they *equal*, or are
they *concurrent* (causally independent — a conflict)?

Missing actors are treated as 0, so clocks with different actor sets compare
cleanly. Pure stdlib; thread-safe via a single non-reentrant ``threading.Lock``.
"""

from __future__ import annotations

import threading
from typing import Mapping


class VectorClock:
    """A vector clock over named actors (stdlib only)."""

    def __init__(self, initial: Mapping[str, int] | None = None) -> None:
        self._clock: dict[str, int] = {}
        self._lock = threading.Lock()
        if initial:
            for actor, value in initial.items():
                iv = int(value)
                if iv < 0:
                    raise ValueError("clock values must be non-negative")
                self._clock[str(actor)] = iv

    # ── mutation ──────────────────────────────────────────────────────────────
    def tick(self, actor: str) -> int:
        """Record a local event for ``actor`` (increment its counter). Returns the new value."""
        actor = str(actor)
        with self._lock:
            self._clock[actor] = self._clock.get(actor, 0) + 1
            return self._clock[actor]

    def merge(self, other: "VectorClock") -> None:
        """Fold ``other`` into this clock via element-wise max (on message receipt)."""
        if not isinstance(other, VectorClock):
            raise ValueError("can only merge another VectorClock")
        snapshot = other.to_dict()
        with self._lock:
            for actor, value in snapshot.items():
                if value > self._clock.get(actor, 0):
                    self._clock[actor] = value

    def clear(self) -> None:
        """Reset the clock to empty."""
        with self._lock:
            self._clock.clear()

    # ── queries ─────────────────────────────────────────────────────────────
    def get(self, actor: str) -> int:
        """Counter for ``actor`` (0 if it has never ticked)."""
        with self._lock:
            return self._clock.get(str(actor), 0)

    def actors(self) -> list[str]:
        """All known actor names, sorted."""
        with self._lock:
            return sorted(self._clock)

    def to_dict(self) -> dict[str, int]:
        """A plain ``{actor: count}`` copy (safe to mutate)."""
        with self._lock:
            return dict(self._clock)

    def copy(self) -> "VectorClock":
        """An independent copy of this clock."""
        return VectorClock(self.to_dict())

    def compare(self, other: "VectorClock") -> str:
        """Causal relation of this clock to ``other``.

        Returns ``"equal"``, ``"before"`` (this happened-before other),
        ``"after"`` (other happened-before this), or ``"concurrent"``.
        """
        if not isinstance(other, VectorClock):
            raise ValueError("can only compare against another VectorClock")
        a = self.to_dict()
        b = other.to_dict()
        less = greater = False
        for actor in set(a) | set(b):
            av, bv = a.get(actor, 0), b.get(actor, 0)
            if av < bv:
                less = True
            elif av > bv:
                greater = True
        if less and greater:
            return "concurrent"
        if less:
            return "before"
        if greater:
            return "after"
        return "equal"

    def stats(self) -> dict:
        """JSON-serialisable snapshot of the clock."""
        with self._lock:
            return {
                "clock": dict(self._clock),
                "actors": sorted(self._clock),
                "actor_count": len(self._clock),
            }
