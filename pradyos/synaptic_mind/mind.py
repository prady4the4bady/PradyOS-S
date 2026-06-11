"""SYNAPTIC MIND model-benchmark and upgrade-proposal engine.

Models carry a composite benchmark ``score`` in ``[0, 1]`` measured on PradyOS's
own workload. ``evaluate`` compares every benchmarked model against the current
default and proposes an upgrade for any that beats it by more than
``UPGRADE_MARGIN`` (relative). ``promote`` swaps the default.
"""

from __future__ import annotations

import threading
from typing import Any

UPGRADE_MARGIN = 0.05  # a candidate must beat the default by >5% to be proposed


class SynapticError(RuntimeError):
    """Base class for SYNAPTIC MIND failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


class _Model:
    __slots__ = ("name", "provider", "score")

    def __init__(self, name: str, provider: str) -> None:
        self.name = name
        self.provider = provider
        self.score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "provider": self.provider, "score": self.score}


class SynapticMind:
    """Benchmarks models and proposes upgrades against the default."""

    def __init__(self) -> None:
        self._models: dict[str, _Model] = {}
        self._default: str | None = None
        self._lock = threading.RLock()

    # ── registry ─────────────────────────────────────────────────────────────

    def register_model(self, name: str, provider: str = "") -> dict[str, Any]:
        if not _is_str(name):
            raise SynapticError("model name must be a non-empty string")
        with self._lock:
            self._models[name] = _Model(name, provider)
            return self._models[name].to_dict()

    def record_benchmark(self, name: str, score: float) -> dict[str, Any]:
        if not isinstance(score, int | float) or not 0.0 <= score <= 1.0:
            raise SynapticError("score must be a number in [0, 1]")
        with self._lock:
            m = self._require(name)
            m.score = float(score)
            return m.to_dict()

    def set_default(self, name: str) -> dict[str, Any]:
        with self._lock:
            self._require(name)
            self._default = name
            return {"default": name}

    def promote(self, name: str) -> dict[str, Any]:
        """Promote ``name`` to the default model."""
        with self._lock:
            self._require(name)
            self._default = name
            return {"default": name, "promoted": name}

    # ── evaluation ───────────────────────────────────────────────────────────

    def evaluate(self) -> dict[str, Any]:
        """Compare benchmarked models against the default; propose upgrades."""
        with self._lock:
            if self._default is None:
                raise SynapticError("no default model set")
            default = self._models[self._default]
            base = default.score
            proposals: list[dict[str, Any]] = []
            if base is not None and base > 0:
                for m in self._models.values():
                    if m.name == self._default or m.score is None:
                        continue
                    improvement = (m.score - base) / base
                    if improvement > UPGRADE_MARGIN:
                        proposals.append(
                            {
                                "model": m.name,
                                "provider": m.provider,
                                "score": m.score,
                                "default_score": base,
                                "improvement": round(improvement, 4),
                            }
                        )
            proposals.sort(key=lambda p: p["improvement"], reverse=True)
            return {
                "default": self._default,
                "default_score": base,
                "proposals": proposals,
                "recommended": proposals[0]["model"] if proposals else None,
            }

    # ── introspection ────────────────────────────────────────────────────────

    def models(self) -> list[dict[str, Any]]:
        with self._lock:
            return [m.to_dict() for m in self._models.values()]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            benchmarked = sum(1 for m in self._models.values() if m.score is not None)
            return {
                "models": len(self._models),
                "benchmarked": benchmarked,
                "default": self._default,
            }

    def reset(self) -> None:
        with self._lock:
            self._models.clear()
            self._default = None

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, name: str) -> _Model:
        m = self._models.get(name)
        if m is None:
            raise SynapticError(f"unknown model {name!r}")
        return m
