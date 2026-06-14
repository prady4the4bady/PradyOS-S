"""CAUSALITY — counterfactual credit assignment (autonomy L5).

FORESIGHT learns *correlation* (this action tends to score well). CAUSALITY asks
the harder question the OS needs for real self-improvement: **did the action cause
the outcome, or just co-occur with it?** It records trials of (causes present,
effects observed) and, for any cause→effect pair, estimates the counterfactual:

    strength = P(effect | cause)  −  P(effect | NOT cause)        (the risk difference)

i.e. "how much more likely was the effect *because* the cause happened" — exactly
the "what if I hadn't done X?" question. A near-zero strength means the cause was
just a bystander; a strongly negative one means it *prevents* the effect.

This is a transparent, deterministic 2×2-contingency estimator (no model, no
network), computed over a bounded buffer of trials so queries stay cheap. It is
deliberately honest about confidence: a pair seen too few times is reported as
``insufficient`` rather than a confident number.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Callable

__all__ = ["CausalEngine", "CausalError"]


class CausalError(RuntimeError):
    """Base class for CAUSALITY failures."""


class CausalEngine:
    """Estimates causal strength + counterfactuals from observed trials."""

    def __init__(self, capacity: int = 2000, min_trials: int = 3, clock: Callable[[], float] | None = None) -> None:
        # each trial: (frozenset(causes), frozenset(effects))
        self._trials: deque[tuple[frozenset[str], frozenset[str]]] = deque(maxlen=capacity)
        self._causes: set[str] = set()
        self._effects: set[str] = set()
        self._min = max(1, int(min_trials))
        import time as _t

        self._clock = clock or _t.time
        self._lock = threading.RLock()

    # ── record ───────────────────────────────────────────────────────────────

    def observe(self, causes: list[str], effects: list[str]) -> dict[str, Any]:
        """Record one trial: the causes that were present and the effects observed.

        An empty trial (no causes, no effects) is VALID and important — it's the
        baseline 'nothing happened' observation that fills the no-cause/no-effect
        cell of the contingency table, without which P(effect|¬cause) is unknowable.
        """
        c = frozenset(str(x).strip() for x in (causes or []) if str(x).strip())
        e = frozenset(str(x).strip() for x in (effects or []) if str(x).strip())
        with self._lock:
            self._trials.append((c, e))
            self._causes |= c
            self._effects |= e
            return {"trials": len(self._trials), "causes": len(self._causes), "effects": len(self._effects)}

    # ── estimate ─────────────────────────────────────────────────────────────

    def _table(self, cause: str, effect: str) -> tuple[int, int, int, int]:
        """2×2 counts: (cause&effect, cause&¬effect, ¬cause&effect, ¬cause&¬effect)."""
        n11 = n10 = n01 = n00 = 0
        for causes, effects in self._trials:
            has_c = cause in causes
            has_e = effect in effects
            if has_c and has_e:
                n11 += 1
            elif has_c and not has_e:
                n10 += 1
            elif (not has_c) and has_e:
                n01 += 1
            else:
                n00 += 1
        return n11, n10, n01, n00

    def counterfactual(self, cause: str, effect: str) -> dict[str, Any]:
        """P(effect|cause), P(effect|¬cause) and their difference (causal strength)."""
        with self._lock:
            n11, n10, n01, n00 = self._table(cause, effect)
        n_cause = n11 + n10
        n_nocause = n01 + n00
        if n_cause < self._min or n_nocause < self._min:
            return {
                "cause": cause,
                "effect": effect,
                "status": "insufficient",
                "n_cause": n_cause,
                "n_without_cause": n_nocause,
                "min_trials": self._min,
            }
        p_with = n11 / n_cause
        p_without = n01 / n_nocause
        strength = p_with - p_without
        return {
            "cause": cause,
            "effect": effect,
            "status": "ok",
            "p_with_cause": round(p_with, 4),
            "p_without_cause": round(p_without, 4),
            "strength": round(strength, 4),
            "interpretation": _interpret(strength),
            "n_cause": n_cause,
            "n_without_cause": n_nocause,
        }

    def strength(self, cause: str, effect: str) -> float:
        cf = self.counterfactual(cause, effect)
        return float(cf["strength"]) if cf.get("status") == "ok" else 0.0

    def attribute(self, effect: str, limit: int = 5) -> list[dict[str, Any]]:
        """Rank candidate causes for an effect by causal strength (strongest first)."""
        with self._lock:
            causes = sorted(self._causes)
        scored = [self.counterfactual(c, effect) for c in causes]
        ok = [s for s in scored if s.get("status") == "ok"]
        ok.sort(key=lambda s: s["strength"], reverse=True)
        return ok[:limit]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "trials": len(self._trials),
                "causes": sorted(self._causes),
                "effects": sorted(self._effects),
                "min_trials": self._min,
            }

    def reset(self) -> None:
        with self._lock:
            self._trials.clear()
            self._causes.clear()
            self._effects.clear()


def _interpret(strength: float) -> str:
    if strength >= 0.5:
        return "strong cause"
    if strength >= 0.15:
        return "likely cause"
    if strength <= -0.5:
        return "strong preventor"
    if strength <= -0.15:
        return "likely preventor"
    return "no clear causal effect (bystander)"
