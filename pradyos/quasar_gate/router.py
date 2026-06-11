"""QUASAR GATE inference router — deterministic backend selection.

The router holds a registry of inference :class:`Backend` configs and, for each
:class:`RouteRequest`, returns the single best backend under a documented,
deterministic policy:

  1. **Capability** — the backend must serve the request's ``task_class``.
  2. **Privacy** — if ``local_only`` is set, remote backends are excluded.
  3. **Latency budget** — if ``max_latency_ms`` is set, backends slower than the
     budget are excluded.
  4. **Health** — backends marked unhealthy are excluded.
  5. **Throttle** — backends already at ``max_concurrent`` in-flight calls are
     excluded (a ``background`` request additionally yields one extra slot of
     headroom to an ``interactive`` request — interactive work is never starved
     by background work).

Surviving candidates are ordered by ``(local-first, cost, latency, name)`` and
the first is chosen. :meth:`candidates` exposes the full ordered list so callers
(and tests) can see the fallback chain. Selection (:meth:`route`) is pure — it
mutates no state; :meth:`acquire` / :meth:`release` manage the in-flight counters
used for throttling, under a lock.

This module is intentionally dependency-free: it decides *where* a task should
run, not *how* — execution belongs to the backend the caller wires in.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from typing import Any

_LOCATIONS = ("local", "remote")
_PRIORITIES = ("interactive", "background")


class QuasarGateError(RuntimeError):
    """Base class for QUASAR GATE failures."""


class NoRouteError(QuasarGateError):
    """No registered backend satisfies the request."""


class UnknownBackendError(QuasarGateError):
    """Referenced a backend that is not registered."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


@dataclass(frozen=True)
class Backend:
    """A registrable inference backend.

    ``capabilities`` is the set of task classes this backend can serve (e.g.
    ``{"code", "chat", "embedding"}``). ``location`` is ``"local"`` or
    ``"remote"``. ``latency_ms`` is the typical end-to-end latency, ``cost`` a
    relative per-call cost (local backends are usually ``0.0``), and
    ``max_concurrent`` the throttle ceiling.
    """

    name: str
    location: str
    capabilities: frozenset[str]
    latency_ms: int
    cost: float = 0.0
    vram_mb: int = 0
    max_concurrent: int = 1

    def __post_init__(self) -> None:
        if not _is_str(self.name):
            raise QuasarGateError("backend name must be a non-empty string")
        if self.location not in _LOCATIONS:
            raise QuasarGateError(f"location must be one of {_LOCATIONS}")
        if not self.capabilities:
            raise QuasarGateError(f"backend {self.name!r} must declare >=1 capability")
        if not all(_is_str(c) for c in self.capabilities):
            raise QuasarGateError("capabilities must be non-empty strings")
        if not isinstance(self.latency_ms, int) or self.latency_ms <= 0:
            raise QuasarGateError("latency_ms must be a positive int")
        if not isinstance(self.cost, int | float) or self.cost < 0:
            raise QuasarGateError("cost must be a non-negative number")
        if not isinstance(self.max_concurrent, int) or self.max_concurrent < 1:
            raise QuasarGateError("max_concurrent must be a positive int")

    @property
    def is_local(self) -> bool:
        return self.location == "local"


@dataclass
class RouteRequest:
    """A task to route.

    ``task_class`` names the kind of work (must match a backend capability).
    ``max_latency_ms`` is an optional latency budget; ``local_only`` forbids
    remote backends (privacy); ``priority`` is ``"interactive"`` or
    ``"background"``.
    """

    task_class: str
    max_latency_ms: int | None = None
    local_only: bool = False
    priority: str = "interactive"

    def __post_init__(self) -> None:
        if not _is_str(self.task_class):
            raise QuasarGateError("task_class must be a non-empty string")
        if self.max_latency_ms is not None and (
            not isinstance(self.max_latency_ms, int) or self.max_latency_ms <= 0
        ):
            raise QuasarGateError("max_latency_ms must be a positive int or None")
        if self.priority not in _PRIORITIES:
            raise QuasarGateError(f"priority must be one of {_PRIORITIES}")


@dataclass
class _Slot:
    backend: Backend
    healthy: bool = True
    inflight: int = 0
    routed: int = 0  # lifetime count of route() selections that picked this backend


@dataclass
class _Stats:
    routes: int = 0
    no_route: int = 0
    by_backend: dict[str, int] = field(default_factory=dict)


class QuasarGate:
    """Inference router: register backends, then route tasks to the best one."""

    def __init__(self) -> None:
        self._slots: dict[str, _Slot] = {}
        self._stats = _Stats()
        self._lock = threading.RLock()

    # ── registration ─────────────────────────────────────────────────────────

    def register_backend(self, backend: Backend) -> None:
        """Register (or replace, by name) a backend. Runtime state is reset."""
        if not isinstance(backend, Backend):
            raise QuasarGateError("register_backend expects a Backend instance")
        with self._lock:
            self._slots[backend.name] = _Slot(backend=backend)

    def register(
        self,
        name: str,
        location: str,
        capabilities: Any,
        latency_ms: int,
        cost: float = 0.0,
        vram_mb: int = 0,
        max_concurrent: int = 1,
    ) -> Backend:
        """Convenience: build a :class:`Backend` and register it."""
        backend = Backend(
            name=name,
            location=location,
            capabilities=frozenset(capabilities),
            latency_ms=latency_ms,
            cost=float(cost),
            vram_mb=vram_mb,
            max_concurrent=max_concurrent,
        )
        self.register_backend(backend)
        return backend

    def remove(self, name: str) -> bool:
        with self._lock:
            return self._slots.pop(name, None) is not None

    def backends(self) -> list[Backend]:
        with self._lock:
            return [slot.backend for slot in self._slots.values()]

    # ── health ───────────────────────────────────────────────────────────────

    def mark_unhealthy(self, name: str) -> None:
        with self._lock:
            self._require(name).healthy = False

    def mark_healthy(self, name: str) -> None:
        with self._lock:
            self._require(name).healthy = True

    def is_healthy(self, name: str) -> bool:
        with self._lock:
            return self._require(name).healthy

    # ── routing ──────────────────────────────────────────────────────────────

    def candidates(self, request: RouteRequest) -> list[Backend]:
        """Return the eligible backends for ``request``, best-first.

        Eligibility applies the capability / privacy / latency / health / throttle
        filters; ordering is ``(local-first, cost, latency_ms, name)``.
        """
        with self._lock:
            eligible = [
                slot.backend for slot in self._slots.values() if self._eligible(slot, request)
            ]
        eligible.sort(key=lambda b: (0 if b.is_local else 1, b.cost, b.latency_ms, b.name))
        return eligible

    def route(self, request: RouteRequest) -> Backend:
        """Select the single best backend for ``request`` (no state mutation).

        Raises :class:`NoRouteError` if nothing is eligible.
        """
        chosen = None
        with self._lock:
            eligible = [
                slot.backend for slot in self._slots.values() if self._eligible(slot, request)
            ]
            if eligible:
                eligible.sort(key=lambda b: (0 if b.is_local else 1, b.cost, b.latency_ms, b.name))
                chosen = eligible[0]
                self._stats.routes += 1
                self._slots[chosen.name].routed += 1
                self._stats.by_backend[chosen.name] = self._stats.by_backend.get(chosen.name, 0) + 1
            else:
                self._stats.no_route += 1
        if chosen is None:
            raise NoRouteError(
                f"no backend serves task_class={request.task_class!r} "
                f"(local_only={request.local_only}, "
                f"max_latency_ms={request.max_latency_ms})"
            )
        return chosen

    def acquire(self, request: RouteRequest) -> Backend:
        """Route ``request`` and reserve an in-flight slot on the chosen backend.

        The reservation is what makes ``max_concurrent`` throttling real: pair
        every :meth:`acquire` with a :meth:`release`. Returns the chosen backend.
        """
        with self._lock:
            eligible = [
                slot.backend for slot in self._slots.values() if self._eligible(slot, request)
            ]
            if not eligible:
                self._stats.no_route += 1
                raise NoRouteError(f"no backend serves task_class={request.task_class!r}")
            eligible.sort(key=lambda b: (0 if b.is_local else 1, b.cost, b.latency_ms, b.name))
            chosen = eligible[0]
            slot = self._slots[chosen.name]
            slot.inflight += 1
            slot.routed += 1
            self._stats.routes += 1
            self._stats.by_backend[chosen.name] = self._stats.by_backend.get(chosen.name, 0) + 1
            return chosen

    def release(self, name: str) -> None:
        """Release one in-flight slot reserved by :meth:`acquire`."""
        with self._lock:
            slot = self._require(name)
            if slot.inflight > 0:
                slot.inflight -= 1

    def inflight(self, name: str) -> int:
        with self._lock:
            return self._require(name).inflight

    # ── introspection ────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "backends": len(self._slots),
                "healthy": sum(1 for s in self._slots.values() if s.healthy),
                "routes": self._stats.routes,
                "no_route": self._stats.no_route,
                "by_backend": dict(self._stats.by_backend),
                "inflight": {n: s.inflight for n, s in self._slots.items()},
            }

    def describe(self, name: str) -> dict[str, Any]:
        with self._lock:
            slot = self._require(name)
            b = slot.backend
            return {
                "name": b.name,
                "location": b.location,
                "capabilities": sorted(b.capabilities),
                "latency_ms": b.latency_ms,
                "cost": b.cost,
                "vram_mb": b.vram_mb,
                "max_concurrent": b.max_concurrent,
                "healthy": slot.healthy,
                "inflight": slot.inflight,
                "routed": slot.routed,
            }

    def reset(self) -> None:
        with self._lock:
            self._slots.clear()
            self._stats = _Stats()

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, name: str) -> _Slot:
        slot = self._slots.get(name)
        if slot is None:
            raise UnknownBackendError(f"unknown backend {name!r}")
        return slot

    def _eligible(self, slot: _Slot, request: RouteRequest) -> bool:
        b = slot.backend
        if request.task_class not in b.capabilities:
            return False
        if request.local_only and not b.is_local:
            return False
        if request.max_latency_ms is not None and b.latency_ms > request.max_latency_ms:
            return False
        if not slot.healthy:
            return False
        # Throttle: interactive work gets one slot of headroom over the ceiling so
        # background work can never fully saturate a backend against it.
        ceiling = b.max_concurrent
        if request.priority == "interactive":
            ceiling += 1
        return slot.inflight < ceiling

    # Convenience for callers that want an immutable snapshot of a backend with a
    # patched field (e.g. for what-if routing) without touching the registry.
    @staticmethod
    def with_overrides(backend: Backend, **overrides: Any) -> Backend:
        return replace(backend, **overrides)
