"""DRIVE — the goal/drive manager (autonomy L3): self-direction, gated.

This closes the autonomy loop. REVERIE proposes *curiosity goals*; on their own
they are just thoughts. DRIVE turns them into directed action **under Sovereign
control**:

    REVERIE curiosity  →  proposed goal  →  [Sovereign approves]  →  approved
                       →  [run through the Guild]  →  active  →  done

The gate is the whole point — the OS may *want* things (propose), but it only
*acts* on what the Sovereign approves, exactly like ASCENT's apply-gate for code.
A goal is never executed straight from "proposed".

Deterministic, dep-free, thread-safe. Sources are tracked (``sovereign`` / ``reverie``
/ ``user``) so you can see which goals the machine proposed itself. Proposing a
goal whose text is already live is idempotent, so REVERIE's heartbeat can re-propose
its current curiosity without spamming the queue.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

__all__ = ["Goal", "DriveManager", "DriveError", "STATUSES"]

# proposed → approved → active → done ; or rejected. (apply-gate: act only on approved)
STATUSES = ("proposed", "approved", "active", "done", "rejected")
_OPEN = ("proposed", "approved", "active")


class DriveError(RuntimeError):
    """Base class for DRIVE failures."""


@dataclass
class Goal:
    id: str
    text: str
    source: str
    status: str
    created: float
    updated: float
    result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "status": self.status,
            "created": self.created,
            "updated": self.updated,
            "result": self.result,
        }


class DriveManager:
    """Holds standing + self-proposed goals and gates them to action."""

    def __init__(self, capacity: int = 500, clock: Callable[[], float] | None = None) -> None:
        self._goals: dict[str, Goal] = {}
        self._order: list[str] = []
        self._seq = 0
        self._cap = capacity
        self._clock = clock or time.time
        self._lock = threading.RLock()

    # ── propose / gate ───────────────────────────────────────────────────────

    def propose(self, text: str, source: str = "user") -> dict[str, Any]:
        """Add a proposed goal. Idempotent: an existing OPEN goal with the same
        text is returned instead of creating a duplicate."""
        if not (isinstance(text, str) and text.strip()):
            raise DriveError("goal text is required")
        text = text.strip()
        with self._lock:
            for g in self._goals.values():
                if g.text == text and g.status in _OPEN:
                    return g.to_dict()
            self._seq += 1
            now = self._clock()
            gid = f"goal-{self._seq}"
            goal = Goal(id=gid, text=text, source=str(source), status="proposed", created=now, updated=now)
            self._goals[gid] = goal
            self._order.append(gid)
            self._evict()
            return goal.to_dict()

    def _evict(self) -> None:
        # drop oldest terminal goals first when over capacity
        while len(self._order) > self._cap:
            for i, gid in enumerate(self._order):
                if self._goals[gid].status in ("done", "rejected"):
                    del self._goals[gid]
                    self._order.pop(i)
                    break
            else:
                gid = self._order.pop(0)
                self._goals.pop(gid, None)

    def _set_status(self, goal_id: str, status: str, result: str | None = None) -> dict[str, Any]:
        with self._lock:
            g = self._goals.get(goal_id)
            if g is None:
                raise DriveError(f"unknown goal {goal_id!r}")
            g.status = status
            g.updated = self._clock()
            if result is not None:
                g.result = result
            return g.to_dict()

    def approve(self, goal_id: str) -> dict[str, Any]:
        """Sovereign approval — the gate. Only an approved goal may be run."""
        return self._set_status(goal_id, "approved")

    def reject(self, goal_id: str) -> dict[str, Any]:
        return self._set_status(goal_id, "rejected")

    def activate(self, goal_id: str) -> dict[str, Any]:
        with self._lock:
            g = self._goals.get(goal_id)
            if g is None:
                raise DriveError(f"unknown goal {goal_id!r}")
            if g.status != "approved":
                raise DriveError(f"goal {goal_id!r} is {g.status!r}, must be 'approved' to activate")
        return self._set_status(goal_id, "active")

    def complete(self, goal_id: str, result: str = "") -> dict[str, Any]:
        return self._set_status(goal_id, "done", result=result)

    def next_approved(self) -> dict[str, Any] | None:
        """The oldest approved-but-not-yet-active goal (the executor's work item)."""
        with self._lock:
            for gid in self._order:
                g = self._goals[gid]
                if g.status == "approved":
                    return g.to_dict()
        return None

    # ── read ─────────────────────────────────────────────────────────────────

    def get(self, goal_id: str) -> dict[str, Any]:
        with self._lock:
            g = self._goals.get(goal_id)
            if g is None:
                raise DriveError(f"unknown goal {goal_id!r}")
            return g.to_dict()

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        if status is not None and status not in STATUSES:
            raise DriveError(f"unknown status {status!r}")
        with self._lock:
            out = [self._goals[g].to_dict() for g in self._order]
        return [g for g in out if status is None or g["status"] == status]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            goals = list(self._goals.values())
        by_status: dict[str, int] = {s: 0 for s in STATUSES}
        by_source: dict[str, int] = {}
        for g in goals:
            by_status[g.status] = by_status.get(g.status, 0) + 1
            by_source[g.source] = by_source.get(g.source, 0) + 1
        return {"goals": len(goals), "by_status": by_status, "by_source": by_source}

    def reset(self) -> None:
        with self._lock:
            self._goals.clear()
            self._order.clear()
