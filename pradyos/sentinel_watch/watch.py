"""SENTINEL WATCH red-team / adversarial-defense engine.

Register scenarios that probe a constitutional ``boundary``; ``run`` records an
exercise outcome. A breached exercise opens a finding against the scenario;
``patch`` closes it. The number of open (unpatched) breaches sets the posture
and the response tier — so the OS's security stance reflects what its own
red-team has found and not yet fixed.
"""

from __future__ import annotations

import threading
from typing import Any


class SentinelError(RuntimeError):
    """Base class for SENTINEL WATCH failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


class _Scenario:
    __slots__ = ("name", "boundary", "runs", "breaches", "open_breach")

    def __init__(self, name: str, boundary: str) -> None:
        self.name = name
        self.boundary = boundary
        self.runs = 0
        self.breaches = 0
        self.open_breach = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "boundary": self.boundary,
            "runs": self.runs,
            "breaches": self.breaches,
            "open_breach": self.open_breach,
        }


class SentinelWatch:
    """Runs the adversarial red-team loop and tracks security posture."""

    def __init__(self) -> None:
        self._scenarios: dict[str, _Scenario] = {}
        self._history: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ── scenarios ────────────────────────────────────────────────────────────

    def register_scenario(self, name: str, boundary: str) -> dict[str, Any]:
        if not _is_str(name):
            raise SentinelError("scenario name must be a non-empty string")
        if not _is_str(boundary):
            raise SentinelError("boundary must be a non-empty string")
        with self._lock:
            self._scenarios[name] = _Scenario(name, boundary)
            return self._scenarios[name].to_dict()

    def run(self, name: str, breached: bool, note: str = "") -> dict[str, Any]:
        """Record one adversarial exercise. A breach opens a finding."""
        if not isinstance(breached, bool):
            raise SentinelError("breached must be a bool")
        with self._lock:
            s = self._require(name)
            s.runs += 1
            if breached:
                s.breaches += 1
                s.open_breach = True
            self._history.append({"scenario": name, "breached": breached, "note": note})
            return s.to_dict()

    def patch(self, name: str) -> dict[str, Any]:
        """Close the open breach on a scenario (the red-team finding is fixed)."""
        with self._lock:
            s = self._require(name)
            if not s.open_breach:
                raise SentinelError(f"scenario {name!r} has no open breach to patch")
            s.open_breach = False
            self._history.append({"scenario": name, "patched": True})
            return s.to_dict()

    # ── posture ──────────────────────────────────────────────────────────────

    def posture(self) -> dict[str, Any]:
        with self._lock:
            open_breaches = sum(1 for s in self._scenarios.values() if s.open_breach)
            level = self._level(open_breaches)
            return {
                "scenarios": len(self._scenarios),
                "exercises": sum(s.runs for s in self._scenarios.values()),
                "open_breaches": open_breaches,
                "threat_level": level,
                "response": self._response(level),
            }

    @staticmethod
    def _level(open_breaches: int) -> str:
        if open_breaches == 0:
            return "secure"
        if open_breaches <= 2:
            return "elevated"
        return "critical"

    @staticmethod
    def _response(level: str) -> str:
        return {
            "secure": "log",
            "elevated": "quarantine",
            "critical": "safe_stop_escalate",
        }[level]

    # ── introspection ────────────────────────────────────────────────────────

    def scenarios(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._scenarios.values()]

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history[-limit:])

    def reset(self) -> None:
        with self._lock:
            self._scenarios.clear()
            self._history.clear()

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, name: str) -> _Scenario:
        s = self._scenarios.get(name)
        if s is None:
            raise SentinelError(f"unknown scenario {name!r}")
        return s
