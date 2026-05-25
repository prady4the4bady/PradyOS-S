"""Health-check registry for PRADY OS.

Provides a singleton registry of named health probes.  Each probe is a
callable that returns a HealthProbe dataclass.  The registry catches all
exceptions and converts them to ``status="down"`` so a faulty probe never
crashes the caller.

Wired into sovereign_web.py as ``GET /api/health``.

Windows-safe: no AF_UNIX, no fork, pure Python threading.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Literal

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class HealthProbe:
    """Result of a single named health check."""

    name: str
    status: Literal["ok", "degraded", "down"]
    latency_ms: float
    detail: str = ""

    def dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ProbeFn = Callable[[], HealthProbe]


class HealthRegistry:
    """Registry of named health probe functions.

    Create via :func:`get_health_registry` to get the process-wide singleton.
    """

    def __init__(self) -> None:
        self._probes: dict[str, ProbeFn] = {}
        self._lock = threading.Lock()

    def register(self, name: str, probe_fn: ProbeFn) -> None:
        """Register a probe callable under *name*."""
        with self._lock:
            self._probes[name] = probe_fn

    def unregister(self, name: str) -> None:
        """Remove a probe by name (no-op if absent)."""
        with self._lock:
            self._probes.pop(name, None)

    def run_all(self) -> list[HealthProbe]:
        """Run every registered probe.

        Exceptions raised by a probe are caught and reported as ``down``.
        Returns results in registration order.
        """
        with self._lock:
            items = list(self._probes.items())

        results: list[HealthProbe] = []
        for name, fn in items:
            t0 = time.monotonic()
            try:
                probe = fn()
                # Ensure latency is realistic even if the probe set its own
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                # Use probe's latency_ms if already set to non-zero, else measure
                if probe.latency_ms == 0.0:
                    probe.latency_ms = elapsed_ms
                results.append(probe)
            except Exception as exc:  # noqa: BLE001
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                results.append(HealthProbe(
                    name=name,
                    status="down",
                    latency_ms=elapsed_ms,
                    detail=f"exception: {exc!r}",
                ))
        return results

    def overall(self) -> Literal["ok", "degraded", "down"]:
        """Aggregate status across all probes.

        * ``ok``       — all probes returned ok
        * ``degraded`` — at least one degraded, none down
        * ``down``     — at least one down
        """
        probes = self.run_all()
        if not probes:
            return "ok"
        statuses = {p.status for p in probes}
        if "down" in statuses:
            return "down"
        if "degraded" in statuses:
            return "degraded"
        return "ok"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton: HealthRegistry | None = None
_singleton_lock = threading.Lock()


def get_health_registry() -> HealthRegistry:
    """Return the process-wide :class:`HealthRegistry` singleton."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = HealthRegistry()
    return _singleton


def reset_health_registry_for_tests() -> HealthRegistry:
    """Reset the singleton — for test isolation only."""
    global _singleton
    with _singleton_lock:
        _singleton = HealthRegistry()
        return _singleton
