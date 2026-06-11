"""QUASAR GATE — inference routing, model placement, and compute arbitration.

Plane 8 of PRADY OS (v5.0 blueprint §4.8 / §5.6 / Part X). QUASAR GATE decides
*which* backend should serve each inference task — local-first, within a latency
budget, capability-matched, health-aware, with ordered fallback and priority
classes. It is the routing **decision** core; actual model execution is delegated
to the chosen backend (injected), so this package stays dependency-free and fully
testable.

Public surface:
    Backend        — a registrable inference backend (config)
    RouteRequest   — a task to route (class, latency budget, privacy, priority)
    QuasarGate     — the router: register backends, route/acquire/release, health
    *Error         — typed failures
"""

from __future__ import annotations

from pradyos.quasar_gate.router import (
    Backend,
    NoRouteError,
    QuasarGate,
    QuasarGateError,
    RouteRequest,
    UnknownBackendError,
)

__all__ = [
    "Backend",
    "RouteRequest",
    "QuasarGate",
    "QuasarGateError",
    "NoRouteError",
    "UnknownBackendError",
]
