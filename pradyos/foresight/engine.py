"""FORESIGHT — a predict → act → compare → learn loop (metacognition).

This is the autonomy layer that makes PradyOS *anticipate and self-correct*
rather than only react. It sits above the planner (oracle), the self-heal engine
(imperium), memory (memory_citadel) and the self-improvement driver (ascent), and
gives them a calibrated sense of "what will happen if I do this, and was I right?"

The loop, after the Reflexion pattern (Shinn et al., 2023) fused with a tiny
world-model:

  1. **Predict.** :class:`WorldModel` estimates the value (0..1 utility) and a
     confidence for each candidate action in a state, blending a prior built from
     past episodes (so experience sharpens foresight).
  2. **Deliberate.** :meth:`ForesightEngine.deliberate` ranks actions by predicted
     value discounted by risk (low confidence) — the OS picks the most promising.
  3. **Act & compare.** After the action runs, the real outcome is recorded; the
     **surprise** = |predicted − actual| measures how wrong the model was.
  4. **Reflect & learn.** A short *lesson* is derived from the error and stored;
     future predictions for similar (state, action) pairs shift toward observed
     reality, and mean surprise (the model's *calibration*) drops over time.

Design matches the rest of the OS: dep-free, deterministic, thread-safe, with the
predictor and memory **injected** so tests use fakes and nothing touches the
network. Pure functions where possible; all shared state lives behind one lock.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
    "Prediction",
    "Outcome",
    "Episode",
    "WorldModel",
    "ForesightEngine",
    "ForesightError",
]


class ForesightError(RuntimeError):
    """Base class for FORESIGHT failures."""


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass(frozen=True)
class Prediction:
    """A forecast for one (state, action): expected utility + how sure we are."""

    expected_value: float  # 0..1 predicted utility
    confidence: float  # 0..1
    rationale: str = ""


@dataclass(frozen=True)
class Outcome:
    """The realised result of an action, as a 0..1 utility (reward)."""

    value: float
    note: str = ""


@dataclass(frozen=True)
class Episode:
    """One full predict→act→compare record — the unit FORESIGHT learns from."""

    state: str
    action: str
    prediction: Prediction
    outcome: Outcome
    surprise: float
    lesson: str
    ts: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "action": self.action,
            "prediction": {
                "expected_value": self.prediction.expected_value,
                "confidence": self.prediction.confidence,
                "rationale": self.prediction.rationale,
            },
            "outcome": {"value": self.outcome.value, "note": self.outcome.note},
            "surprise": self.surprise,
            "lesson": self.lesson,
            "ts": self.ts,
        }


def _key(state: str, action: str) -> str:
    return f"{state.strip().lower()}\x1f{action.strip().lower()}"


class WorldModel:
    """Predicts an action's value, sharpening as episodes accumulate.

    A custom ``predictor(state, action, prior) -> Prediction`` can be injected
    (e.g. an LLM-backed estimator); by default a transparent heuristic blends a
    neutral prior (0.5) with the mean realised value of past similar episodes,
    growing confidence with the number of samples seen.
    """

    def __init__(
        self,
        predictor: Callable[[str, str, tuple[float, int]], Prediction] | None = None,
    ) -> None:
        self._predictor = predictor

    def predict(self, state: str, action: str, prior: tuple[float, int]) -> Prediction:
        if self._predictor is not None:
            return self._predictor(state, action, prior)
        mean, n = prior
        if n <= 0:
            return Prediction(0.5, 0.2, "no prior experience — neutral guess")
        # blend toward observed mean; confidence rises with sample count (caps ~0.9)
        weight = min(0.85, n / (n + 3))
        expected = _clamp(0.5 * (1 - weight) + mean * weight)
        confidence = _clamp(0.2 + 0.7 * (n / (n + 4)))
        return Prediction(expected, confidence, f"prior mean {mean:.2f} over {n} episode(s)")


class ForesightEngine:
    """The predict→deliberate→act→reflect loop with a learning memory."""

    def __init__(
        self,
        world_model: WorldModel | None = None,
        risk_aversion: float = 0.35,
        capacity: int = 500,
        clock: Callable[[], float] | None = None,
        on_observe: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self._wm = world_model or WorldModel()
        self._risk = float(risk_aversion)
        self._clock = clock or time.time
        self._episodes: deque[Episode] = deque(maxlen=capacity)
        # Optional hook(episode_dict) fired after each observation — used to feed
        # CAUSALITY (action→outcome trials). Best-effort; never sinks an observe.
        self._on_observe = on_observe
        self._lock = threading.RLock()

    # ── priors / recall ──────────────────────────────────────────────────────

    def prior(self, state: str, action: str) -> tuple[float, int]:
        """(mean realised value, sample count) for a (state, action) pair."""
        k = _key(state, action)
        with self._lock:
            vals = [e.outcome.value for e in self._episodes if _key(e.state, e.action) == k]
        if not vals:
            return (0.0, 0)
        return (sum(vals) / len(vals), len(vals))

    def predict(self, state: str, action: str) -> Prediction:
        return self._wm.predict(state, action, self.prior(state, action))

    def recall(self, action: str, limit: int = 5) -> list[Episode]:
        """Most-recent episodes for an action (the reflective context)."""
        a = action.strip().lower()
        with self._lock:
            hits = [e for e in self._episodes if e.action.strip().lower() == a]
        return list(reversed(hits))[:limit]

    # ── deliberate ───────────────────────────────────────────────────────────

    def deliberate(self, state: str, actions: list[str]) -> dict[str, Any]:
        """Score candidate actions and choose. Score = predicted value − risk×(1−confidence)."""
        if not actions:
            raise ForesightError("deliberate needs at least one candidate action")
        ranked: list[dict[str, Any]] = []
        for a in actions:
            p = self.predict(state, a)
            score = _clamp(p.expected_value - self._risk * (1 - p.confidence), -1, 1)
            ranked.append(
                {
                    "action": a,
                    "expected_value": p.expected_value,
                    "confidence": p.confidence,
                    "score": round(score, 4),
                    "rationale": p.rationale,
                }
            )
        ranked.sort(key=lambda r: r["score"], reverse=True)
        return {"chosen": ranked[0]["action"], "ranked": ranked}

    # ── act & learn ──────────────────────────────────────────────────────────

    def observe(
        self,
        state: str,
        action: str,
        outcome_value: float,
        *,
        note: str = "",
        prediction: Prediction | None = None,
    ) -> Episode:
        """Record the realised outcome of an action and learn from the error."""
        outcome = Outcome(_clamp(float(outcome_value)), note)
        pred = prediction or self.predict(state, action)
        surprise = round(abs(pred.expected_value - outcome.value), 4)
        lesson = self._lesson(pred, outcome, surprise)
        ep = Episode(
            state=state,
            action=action,
            prediction=pred,
            outcome=outcome,
            surprise=surprise,
            lesson=lesson,
            ts=self._clock(),
        )
        with self._lock:
            self._episodes.append(ep)
        # Feed the outcome to a downstream learner (CAUSALITY). Best-effort.
        if self._on_observe is not None:
            try:
                self._on_observe(ep.to_dict())
            except Exception:  # noqa: BLE001 — a bad hook must not sink the observation
                pass
        return ep

    @staticmethod
    def _lesson(pred: Prediction, outcome: Outcome, surprise: float) -> str:
        if surprise < 0.15:
            return "well-calibrated — the model anticipated this outcome"
        direction = "worse" if outcome.value < pred.expected_value else "better"
        return (
            f"outcome was {direction} than predicted "
            f"({outcome.value:.2f} vs {pred.expected_value:.2f}); "
            f"adjust expectations for this action"
        )

    # ── introspection ────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            eps = list(self._episodes)
        n = len(eps)
        mean_surprise = round(sum(e.surprise for e in eps) / n, 4) if n else 0.0
        # calibration: recent surprise vs. early surprise (is the model learning?)
        recent = eps[-10:]
        recent_surprise = (
            round(sum(e.surprise for e in recent) / len(recent), 4) if recent else 0.0
        )
        return {
            "episodes": n,
            "mean_surprise": mean_surprise,
            "recent_surprise": recent_surprise,
            "calibration": round(1 - recent_surprise, 4),
            "lessons": [e.lesson for e in eps[-5:]],
        }

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            eps = list(self._episodes)[-limit:]
        return [e.to_dict() for e in reversed(eps)]

    def reset(self) -> None:
        with self._lock:
            self._episodes.clear()
