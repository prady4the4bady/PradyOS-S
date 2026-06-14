"""FORESIGHT L2 — an LLM-backed world-model predictor.

The default :class:`~pradyos.foresight.engine.WorldModel` is frequentist: it can
only predict actions it has *already seen* (it blends a prior from past episodes).
This module gives FORESIGHT **semantic foresight** — it asks the pluggable model
(:mod:`pradyos.core.llm`, local Ollama by default) to estimate the value and
confidence of an action *in context*, so the OS can reason about novel states it
has no statistics for.

It stays safe and honest:

  * **Prior-anchored.** The episode prior is given to the model and returned as the
    fallback, so a model that refuses/echoes never erases hard-won experience.
  * **Fail-soft.** Any error (no model, timeout, unparseable output, out-of-range
    numbers) falls back to the deterministic heuristic — FORESIGHT never breaks
    because a model is slow or absent.
  * **Opt-in.** Wired only when ``PRADYOS_FORESIGHT_LLM`` is set; the default OS
    keeps the fast, offline heuristic.

The provider is injected (anything with ``generate(prompt, *, system=...) -> str``),
so tests use a fake and nothing touches the network.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pradyos.foresight.engine import Prediction, WorldModel

_SYSTEM = (
    "You are PRADYOS's world-model. Estimate the outcome of an ACTION in a STATE. "
    "Reply with ONLY compact JSON: "
    '{"value": <0..1 expected utility>, "confidence": <0..1>, "rationale": "<short>"}. '
    "Use the prior (mean realised value over N past episodes) as an anchor."
)


def _heuristic(prior: tuple[float, int]) -> Prediction:
    """The same prior-blend the default WorldModel uses — the safe fallback."""
    mean, n = prior
    if n <= 0:
        return Prediction(0.5, 0.2, "no prior; model unavailable — neutral")
    weight = min(0.85, n / (n + 3))
    expected = max(0.0, min(1.0, 0.5 * (1 - weight) + mean * weight))
    confidence = max(0.0, min(1.0, 0.2 + 0.7 * (n / (n + 4))))
    return Prediction(expected, confidence, f"fallback: prior {mean:.2f} over {n}")


def _extract_json(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model reply (tolerant of prose/fences)."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001 — try to find an embedded object
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return None


def _clamp01(x: Any, default: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return 0.0 if v < 0 else 1.0 if v > 1 else v


class LLMPredictor:
    """A FORESIGHT predictor backed by the pluggable model (fail-soft to heuristic)."""

    def __init__(self, provider: Any, temperature: float = 0.1) -> None:
        if provider is None or not hasattr(provider, "generate"):
            raise ValueError("LLMPredictor needs a provider with a generate() method")
        self._provider = provider
        self._temperature = temperature

    def __call__(self, state: str, action: str, prior: tuple[float, int]) -> Prediction:
        mean, n = prior
        prompt = (
            f"STATE: {state}\nACTION: {action}\n"
            f"PRIOR: mean realised value {mean:.2f} over {n} past episode(s).\n"
            "Estimate the outcome as JSON."
        )
        try:
            raw = self._provider.generate(prompt, system=_SYSTEM, temperature=self._temperature)
        except Exception:  # noqa: BLE001 — model down/timeout → heuristic
            return _heuristic(prior)
        data = _extract_json(raw)
        if not isinstance(data, dict) or "value" not in data:
            return _heuristic(prior)
        value = _clamp01(data.get("value"), _heuristic(prior).expected_value)
        confidence = _clamp01(data.get("confidence"), 0.5)
        rationale = str(data.get("rationale", "llm world-model"))[:200]
        return Prediction(value, confidence, rationale)


def make_llm_world_model(provider: Any, temperature: float = 0.1) -> WorldModel:
    """Build a :class:`WorldModel` whose predictor is the injected LLM provider."""
    return WorldModel(predictor=LLMPredictor(provider, temperature=temperature))
