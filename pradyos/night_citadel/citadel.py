"""NIGHT CITADEL self-improvement cycle orchestrator.

A cycle walks the ordered ``PHASES``. ``advance`` enforces the safety gates: it
raises :class:`CitadelError` if the data a gate needs hasn't been recorded yet,
and it HALTS the cycle (phase ``halted`` with a reason) if a gate *fails* —
never promoting a risky self-modification. A cycle that clears all gates reaches
``promoted``.
"""

from __future__ import annotations

import threading
from typing import Any

# ``idle`` is the dormant state (index 0) before a cycle is initiated; a created
# ``_Cycle`` starts already-initiated at ``auditing``. It is kept in PHASES so the
# exposed ``phase_index`` stays stable and an idle citadel is representable.
PHASES: tuple[str, ...] = (
    "idle",
    "auditing",
    "generating",
    "drift_check",
    "constraint_check",
    "regression_check",
    "staging",
    "promoted",
)

GDI_THRESHOLD = 0.15
REGRESSION_THRESHOLD = 0.02


class CitadelError(RuntimeError):
    """Base class for NIGHT CITADEL failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


class _Cycle:
    __slots__ = (
        "id",
        "phase",
        "failures",
        "candidates",
        "gdi",
        "constraints_ok",
        "regression",
        "halt_reason",
    )

    def __init__(self, cycle_id: str) -> None:
        self.id = cycle_id
        self.phase = "auditing"  # initiation moves straight into the audit phase
        self.failures: list[str] = []
        self.candidates: list[dict[str, str]] = []
        self.gdi: float | None = None
        self.constraints_ok: bool | None = None
        self.regression: float | None = None
        self.halt_reason: str | None = None

    def manifest(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "phase": self.phase,
            "phase_index": PHASES.index(self.phase) if self.phase in PHASES else -1,
            "failures": list(self.failures),
            "candidates": [dict(c) for c in self.candidates],
            "gdi": self.gdi,
            "constraints_ok": self.constraints_ok,
            "regression": self.regression,
            "halted": self.phase == "halted",
            "halt_reason": self.halt_reason,
            "promoted": self.phase == "promoted",
        }


class NightCitadel:
    """Runs safeguarded self-improvement cycles."""

    def __init__(self) -> None:
        self._cycles: dict[str, _Cycle] = {}
        self._lock = threading.RLock()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start_cycle(self, cycle_id: str) -> dict[str, Any]:
        if not _is_str(cycle_id):
            raise CitadelError("cycle_id must be a non-empty string")
        with self._lock:
            if cycle_id in self._cycles:
                raise CitadelError(f"cycle {cycle_id!r} already exists")
            c = _Cycle(cycle_id)
            self._cycles[cycle_id] = c
            return c.manifest()

    def record_audit(self, cycle_id: str, failures: Any) -> dict[str, Any]:
        if not isinstance(failures, list | tuple) or not all(isinstance(f, str) for f in failures):
            raise CitadelError("failures must be a list of strings")
        with self._lock:
            c = self._require(cycle_id)
            c.failures = list(failures)
            return c.manifest()

    def add_candidate(self, cycle_id: str, name: str, target: str = "") -> dict[str, Any]:
        if not _is_str(name):
            raise CitadelError("candidate name must be a non-empty string")
        with self._lock:
            c = self._require(cycle_id)
            c.candidates.append({"name": name, "target": target})
            return c.manifest()

    def set_gdi(self, cycle_id: str, gdi: float) -> dict[str, Any]:
        if not isinstance(gdi, int | float) or gdi < 0:
            raise CitadelError("gdi must be a non-negative number")
        with self._lock:
            self._require(cycle_id).gdi = float(gdi)
            return self._cycles[cycle_id].manifest()

    def set_constraints_ok(self, cycle_id: str, ok: bool) -> dict[str, Any]:
        if not isinstance(ok, bool):
            raise CitadelError("ok must be a bool")
        with self._lock:
            self._require(cycle_id).constraints_ok = ok
            return self._cycles[cycle_id].manifest()

    def set_regression(self, cycle_id: str, regression: float) -> dict[str, Any]:
        if not isinstance(regression, int | float) or regression < 0:
            raise CitadelError("regression must be a non-negative number")
        with self._lock:
            self._require(cycle_id).regression = float(regression)
            return self._cycles[cycle_id].manifest()

    def advance(self, cycle_id: str) -> dict[str, Any]:
        """Move to the next phase, enforcing the gates (raise on missing data,
        HALT on gate failure)."""
        with self._lock:
            c = self._require(cycle_id)
            if c.phase in ("halted", "promoted"):
                raise CitadelError(f"cycle {cycle_id!r} is terminal ({c.phase})")
            idx = PHASES.index(c.phase)
            nxt = PHASES[idx + 1]

            if nxt == "drift_check":
                if not c.candidates:
                    raise CitadelError("cannot proceed: no improvement candidates")
            if c.phase == "drift_check":
                if c.gdi is None:
                    raise CitadelError("set gdi before leaving drift_check")
                if c.gdi > GDI_THRESHOLD:
                    return self._halt(c, f"GDI {c.gdi} > {GDI_THRESHOLD} (drift gate)")
            if c.phase == "constraint_check":
                if c.constraints_ok is None:
                    raise CitadelError("set constraints_ok before leaving constraint_check")
                if not c.constraints_ok:
                    return self._halt(c, "constitutional constraints failed")
            if c.phase == "regression_check":
                if c.regression is None:
                    raise CitadelError("set regression before leaving regression_check")
                if c.regression > REGRESSION_THRESHOLD:
                    return self._halt(c, f"regression {c.regression} > {REGRESSION_THRESHOLD}")

            c.phase = nxt
            return c.manifest()

    def halt(self, cycle_id: str, reason: str) -> dict[str, Any]:
        with self._lock:
            return self._halt(self._require(cycle_id), reason or "manual halt")

    # ── introspection ────────────────────────────────────────────────────────

    def manifest(self, cycle_id: str) -> dict[str, Any]:
        with self._lock:
            return self._require(cycle_id).manifest()

    def cycles(self) -> list[dict[str, Any]]:
        with self._lock:
            return [c.manifest() for c in self._cycles.values()]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_phase: dict[str, int] = {}
            for c in self._cycles.values():
                by_phase[c.phase] = by_phase.get(c.phase, 0) + 1
            return {"cycles": len(self._cycles), "by_phase": by_phase}

    def reset(self) -> None:
        with self._lock:
            self._cycles.clear()

    # ── internals ────────────────────────────────────────────────────────────

    def _halt(self, c: _Cycle, reason: str) -> dict[str, Any]:
        c.phase = "halted"
        c.halt_reason = reason
        return c.manifest()

    def _require(self, cycle_id: str) -> _Cycle:
        c = self._cycles.get(cycle_id)
        if c is None:
            raise CitadelError(f"unknown cycle {cycle_id!r}")
        return c
