"""An LLM-backed reflector for REVERIE (autonomy L6).

The default REVERIE reflection is a deterministic template ("Investigate why action
X is hard to predict"). This lets the pluggable model (:mod:`pradyos.core.llm`) write
a sharper, context-aware **curiosity goal** from the same assembled signals
(calibration, the blind spot, the weakest skill) — a richer "what should I look
into next?" than a template can produce.

Fail-soft: any error (no model, timeout, empty/garbage reply) returns ``None`` so
REVERIE keeps its deterministic goal. Opt-in via ``PRADYOS_REVERIE_LLM``. The
provider is injected, so tests use a fake and nothing touches the network.
"""

from __future__ import annotations

from typing import Any, Callable

_SYSTEM = (
    "You are PRADYOS reflecting on its own cognition during idle time. Given the "
    "OS's calibration, its biggest blind spot, and its weakest skill, propose ONE "
    "concrete curiosity goal to investigate next — a single imperative sentence, no "
    "preamble, under 140 characters."
)


def make_llm_reflector(provider: Any, temperature: float = 0.4) -> Callable[[dict[str, Any]], str | None]:
    """Return ``reflector(context) -> str|None`` backed by ``provider`` (fail-soft)."""
    if provider is None or not hasattr(provider, "generate"):
        raise ValueError("make_llm_reflector needs a provider with a generate() method")

    def _reflect(context: dict[str, Any]) -> str | None:
        blind = context.get("blind_spot")
        weak = context.get("weakest_skill")
        prompt = (
            f"calibration: {context.get('calibration')}\n"
            f"episodes: {context.get('episodes')}\n"
            f"blind_spot: {blind}\n"
            f"weakest_skill: {weak}\n"
            f"skills_known: {context.get('skills')}\n"
            "Propose the curiosity goal."
        )
        try:
            out = provider.generate(prompt, system=_SYSTEM, temperature=temperature)
        except Exception:  # noqa: BLE001 — model down/timeout → keep heuristic
            return None
        if not isinstance(out, str):
            return None
        goal = out.strip().strip('"').splitlines()[0].strip() if out.strip() else ""
        return goal[:200] or None

    return _reflect
