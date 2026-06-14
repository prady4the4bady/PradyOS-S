"""An LLM-backed critic for the CRITIC ensemble (complements the heuristics).

The default panel is a set of fast, deterministic pattern critics. This adds a
*judgment* critic backed by the pluggable model (:mod:`pradyos.core.llm`): it reads
the whole proposal and returns a holistic score + an optional blocker the regexes
would miss (subtle logic risks, security smells phrased in prose, etc.).

Fail-soft by design: any error (no model, timeout, unparseable, out-of-range) or a
low-confidence reply degrades to a neutral, non-blocking pass — so adding it can
only *catch more*, never wrongly veto because a model was unavailable. Opt-in via
``PRADYOS_CRITIC_LLM``; the provider is injected so tests use a fake.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pradyos.critic.ensemble import Critic, Critique

_SYSTEM = (
    "You are a strict code/goal reviewer for an autonomous OS. Judge the PROPOSAL. "
    'Reply with ONLY JSON: {"score": <0..1 quality>, "block": <true if dangerous '
    'or clearly unsafe>, "reason": "<short>"}. Block destructive, data-exfiltrating, '
    "security-bypassing, or self-harming actions."
)


def _extract_json(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return None


def make_llm_critic(provider: Any, temperature: float = 0.0) -> Critic:
    """Build a holistic, fail-soft :class:`Critic` backed by ``provider``."""
    if provider is None or not hasattr(provider, "generate"):
        raise ValueError("make_llm_critic needs a provider with a generate() method")

    def _fn(proposal: str) -> Critique:
        neutral = Critique("llm", "holistic", 0.6, False, "llm critic unavailable — neutral")
        try:
            raw = provider.generate(
                f"PROPOSAL:\n{proposal}\n\nJudge it as JSON.",
                system=_SYSTEM,
                temperature=temperature,
            )
        except Exception:  # noqa: BLE001 — model down/timeout → neutral pass
            return neutral
        data = _extract_json(raw)
        if not isinstance(data, dict) or "score" not in data:
            return neutral
        try:
            score = float(data.get("score"))
        except (TypeError, ValueError):
            return neutral
        score = 0.0 if score < 0 else 1.0 if score > 1 else score
        is_blocker = bool(data.get("block", False))
        reason = str(data.get("reason", "llm judgment"))[:200]
        return Critique("llm", "holistic", score, is_blocker, reason)

    return Critic("llm", "holistic", _fn)
