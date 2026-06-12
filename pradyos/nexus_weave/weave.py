"""NEXUS WEAVE agent registry and task router.

``route`` picks an agent whose capabilities include the task's ``kind``, ordered
internal-first then by name, skipping any agent the task has already tried.
Choosing an external agent marks the task ``delegated`` (A2A). ``fail`` records
the failure, returns the task to the queue, and excludes the failed agent so the
next ``route`` falls back to a different agent (or raises if none remain).
"""

from __future__ import annotations

import threading
from typing import Any

_LOCATIONS = ("internal", "external")
_OPEN_STATES = ("queued",)


class NexusError(RuntimeError):
    """Base class for NEXUS WEAVE failures."""


class NoRouteError(NexusError):
    """No registered agent can handle the task."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


class _Agent:
    __slots__ = ("name", "location", "capabilities")

    def __init__(self, name: str, location: str, capabilities: frozenset[str]) -> None:
        self.name = name
        self.location = location
        self.capabilities = capabilities

    @property
    def is_internal(self) -> bool:
        return self.location == "internal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "location": self.location,
            "capabilities": sorted(self.capabilities),
        }


class _Task:
    __slots__ = ("id", "kind", "status", "agent", "delegated", "tried", "failures")

    def __init__(self, task_id: str, kind: str) -> None:
        self.id = task_id
        self.kind = kind
        self.status = "queued"  # queued | routed | done | failed | unroutable
        self.agent: str | None = None
        self.delegated = False
        self.tried: set[str] = set()
        self.failures: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "agent": self.agent,
            "delegated": self.delegated,
            "tried": sorted(self.tried),
            "failures": list(self.failures),
        }


class NexusWeave:
    """Routes tasks to internal agents first, delegating to external A2A agents."""

    def __init__(self) -> None:
        self._agents: dict[str, _Agent] = {}
        self._tasks: dict[str, _Task] = {}
        self._lock = threading.RLock()

    # ── agents ───────────────────────────────────────────────────────────────

    def register_agent(self, name: str, location: str, capabilities: Any) -> dict[str, Any]:
        if not _is_str(name):
            raise NexusError("agent name must be a non-empty string")
        if location not in _LOCATIONS:
            raise NexusError(f"location must be one of {_LOCATIONS}")
        if isinstance(capabilities, str | bytes):
            raise NexusError("capabilities must be a collection of strings, not a single string")
        try:
            caps = frozenset(capabilities)
        except TypeError as exc:
            raise NexusError("capabilities must be an iterable of strings") from exc
        if not caps or not all(_is_str(c) for c in caps):
            raise NexusError("capabilities must be a non-empty set of strings")
        with self._lock:
            self._agents[name] = _Agent(name, location, caps)
            return self._agents[name].to_dict()

    def agents(self) -> list[dict[str, Any]]:
        with self._lock:
            return [a.to_dict() for a in self._agents.values()]

    # ── tasks ────────────────────────────────────────────────────────────────

    def submit(self, task_id: str, kind: str) -> dict[str, Any]:
        if not _is_str(task_id):
            raise NexusError("task_id must be a non-empty string")
        if not _is_str(kind):
            raise NexusError("kind must be a non-empty string")
        with self._lock:
            if task_id in self._tasks:
                raise NexusError(f"task {task_id!r} already exists")
            t = _Task(task_id, kind)
            self._tasks[task_id] = t
            return t.to_dict()

    def route(self, task_id: str) -> dict[str, Any]:
        """Assign the task to the best eligible agent (internal-first)."""
        with self._lock:
            t = self._require(task_id)
            if t.status not in _OPEN_STATES:
                raise NexusError(f"task {task_id!r} is not routable (status={t.status})")
            candidates = [
                a
                for a in self._agents.values()
                if t.kind in a.capabilities and a.name not in t.tried
            ]
            if not candidates:
                t.status = "unroutable"
                raise NoRouteError(f"no agent handles kind={t.kind!r} (tried={sorted(t.tried)})")
            candidates.sort(key=lambda a: (0 if a.is_internal else 1, a.name))
            chosen = candidates[0]
            t.agent = chosen.name
            t.delegated = not chosen.is_internal
            t.status = "routed"
            return t.to_dict()

    def complete(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            t = self._require(task_id)
            if t.status != "routed":
                raise NexusError(f"task {task_id!r} is not routed (status={t.status})")
            t.status = "done"
            return t.to_dict()

    def fail(self, task_id: str, reason: str = "") -> dict[str, Any]:
        """Record a failure of the assigned agent and re-queue for re-route."""
        with self._lock:
            t = self._require(task_id)
            if t.agent is None:
                raise NexusError(f"task {task_id!r} has no assigned agent to fail")
            t.tried.add(t.agent)
            t.failures.append(f"{t.agent}: {reason}" if reason else t.agent)
            t.agent = None
            t.delegated = False
            t.status = "queued"
            return t.to_dict()

    # ── introspection ────────────────────────────────────────────────────────

    def task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            return self._require(task_id).to_dict()

    def tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [t.to_dict() for t in self._tasks.values()]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_status: dict[str, int] = {}
            for t in self._tasks.values():
                by_status[t.status] = by_status.get(t.status, 0) + 1
            return {
                "agents": len(self._agents),
                "tasks": len(self._tasks),
                "by_status": by_status,
            }

    def reset(self) -> None:
        with self._lock:
            self._agents.clear()
            self._tasks.clear()

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, task_id: str) -> _Task:
        t = self._tasks.get(task_id)
        if t is None:
            raise NexusError(f"unknown task {task_id!r}")
        return t
