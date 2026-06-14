"""REVERIE — the OS's idle cognition loop (a NEW autonomy feature).

Where ASCENT's driver is the *code* ouroboros (the OS reads its own source and
proposes self-hardening), REVERIE is the *cognitive* ouroboros: a background pass
that reflects on the OS's own **thinking** and turns it into direction.

Each reflection fuses three existing signals — no new store, no duplication:

  * **FORESIGHT calibration & blind spots** — how well the OS predicts outcomes,
    and which action it is currently *most surprised by* (its biggest blind spot).
  * **The skill library** — how much competence has accumulated and which skill is
    weakest (a prune/improve candidate).
  * **Curiosity (intrinsic motivation)** — a self-proposed goal aimed at the blind
    spot or the weakest skill, so the OS explores what it understands least. This
    is the engine of open-ended growth (cf. intrinsic-motivation RL; Schmidhuber's
    formal curiosity; Generative Agents' reflection).

The output is an *insight* — a small, inspectable thought the Sovereign can read
and (optionally) promote into a real objective. REVERIE never acts on its own;
it proposes. Deterministic, dep-free, thread-safe; the engines are injected so a
reflection touches no network and is fully unit-testable.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Callable

__all__ = ["Reverie", "ReverieError"]


class ReverieError(RuntimeError):
    """Base class for REVERIE failures."""


class Reverie:
    """Reflects on FORESIGHT + the skill library to produce insights & curiosity."""

    def __init__(
        self,
        foresight: Any | None = None,
        skills: Any | None = None,
        capacity: int = 50,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._fs = foresight
        self._skills = skills
        self._insights: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.RLock()
        import time as _t

        self._clock = clock or _t.time

    # ── reflect ──────────────────────────────────────────────────────────────

    def _blind_spot(self) -> dict[str, Any] | None:
        """The recent episode the OS was most wrong about (highest surprise)."""
        if self._fs is None:
            return None
        try:
            history = self._fs.history(limit=30)
        except Exception:  # noqa: BLE001
            return None
        if not history:
            return None
        worst = max(history, key=lambda e: e.get("surprise", 0.0))
        if worst.get("surprise", 0.0) < 0.2:  # nothing notably surprising
            return None
        return {"action": worst.get("action"), "surprise": worst.get("surprise"), "state": worst.get("state")}

    def _weakest_skill(self) -> dict[str, Any] | None:
        if self._skills is None:
            return None
        try:
            skills = self._skills.skills()
        except Exception:  # noqa: BLE001
            return None
        tried = [s for s in skills if s.get("attempts", 0) >= 1]
        if not tried:
            return None
        weak = min(tried, key=lambda s: s.get("confidence", 1.0))
        return {"id": weak.get("id"), "name": weak.get("name"), "confidence": weak.get("confidence")}

    def reflect(self) -> dict[str, Any]:
        """Produce one insight: calibration, blind spot, weakest skill, curiosity."""
        fs_stats: dict[str, Any] = {}
        if self._fs is not None:
            try:
                fs_stats = self._fs.stats()
            except Exception:  # noqa: BLE001
                fs_stats = {}
        sk_stats: dict[str, Any] = {}
        if self._skills is not None:
            try:
                sk_stats = self._skills.stats()
            except Exception:  # noqa: BLE001
                sk_stats = {}

        blind = self._blind_spot()
        weak = self._weakest_skill()

        if blind is not None:
            curiosity = f"Investigate why action '{blind['action']}' is hard to predict (surprise {blind['surprise']})"
            focus = "blind_spot"
        elif weak is not None:
            curiosity = f"Strengthen the weak skill '{weak['name']}' (confidence {weak['confidence']})"
            focus = "weak_skill"
        elif not (sk_stats.get("skills") or fs_stats.get("episodes")):
            curiosity = "Acquire first experience: run an objective through the Guild to seed skills + foresight"
            focus = "cold_start"
        else:
            curiosity = "Consolidate: rehearse a proven skill to keep calibration high"
            focus = "consolidate"

        insight = {
            "ts": self._clock(),
            "focus": focus,
            "calibration": fs_stats.get("calibration"),
            "episodes": fs_stats.get("episodes", 0),
            "blind_spot": blind,
            "weakest_skill": weak,
            "skills": sk_stats.get("skills", 0),
            "curiosity_goal": curiosity,
        }
        with self._lock:
            self._insights.append(insight)
        return insight

    # ── introspection ────────────────────────────────────────────────────────

    def insights(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._insights)[-limit:][::-1]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            items = list(self._insights)
        foci: dict[str, int] = {}
        for i in items:
            foci[i["focus"]] = foci.get(i["focus"], 0) + 1
        return {
            "reflections": len(items),
            "by_focus": foci,
            "latest_goal": items[-1]["curiosity_goal"] if items else None,
        }

    def reset(self) -> None:
        with self._lock:
            self._insights.clear()
