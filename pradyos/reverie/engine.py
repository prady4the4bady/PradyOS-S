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
        on_curiosity: Callable[[str], Any] | None = None,
        reflector: Callable[[dict[str, Any]], str | None] | None = None,
    ) -> None:
        self._fs = foresight
        self._skills = skills
        self._insights: deque[dict[str, Any]] = deque(maxlen=capacity)
        # Optional hook(curiosity_goal:str) — fired on each reflection so a higher
        # layer (DRIVE) can propose the goal for Sovereign approval. Best-effort.
        self._on_curiosity = on_curiosity
        # Optional reflector(context)->str|None (L6) — an LLM that writes a sharper
        # curiosity goal from the signals; None ⇒ the deterministic heuristic.
        self._reflector = reflector
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

        context = {
            "focus": focus,
            "calibration": fs_stats.get("calibration"),
            "episodes": fs_stats.get("episodes", 0),
            "blind_spot": blind,
            "weakest_skill": weak,
            "skills": sk_stats.get("skills", 0),
        }
        # L6: let an LLM reflector write a sharper goal; fall back to the heuristic.
        source = "heuristic"
        if self._reflector is not None:
            try:
                llm_goal = self._reflector(context)
            except Exception:  # noqa: BLE001
                llm_goal = None
            if llm_goal:
                curiosity = llm_goal
                source = "llm"

        insight = {**context, "ts": self._clock(), "curiosity_goal": curiosity, "source": source}
        with self._lock:
            self._insights.append(insight)
        # Surface the curiosity goal to DRIVE (proposed for Sovereign approval).
        if self._on_curiosity is not None:
            try:
                self._on_curiosity(curiosity)
            except Exception:  # noqa: BLE001 — proposing must not break reflection
                pass
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

    def consolidate(self, limit: int = 20) -> dict[str, Any]:
        """Memory consolidation (L6): distil recent insights into one standing
        directive — the dominant recurring focus + its most recent goal — so the
        OS keeps a stable theme instead of chasing each reflection in isolation."""
        with self._lock:
            recent = list(self._insights)[-limit:]
        if not recent:
            return {"status": "empty", "dominant_focus": None, "themes": [], "standing_directive": None}
        by_focus: dict[str, int] = {}
        latest_goal_for: dict[str, str] = {}
        for ins in recent:
            f = ins["focus"]
            by_focus[f] = by_focus.get(f, 0) + 1
            latest_goal_for[f] = ins["curiosity_goal"]
        dominant = max(by_focus, key=lambda k: by_focus[k])
        themes = sorted(
            ({"focus": f, "count": n, "goal": latest_goal_for[f]} for f, n in by_focus.items()),
            key=lambda t: t["count"],
            reverse=True,
        )
        return {
            "status": "ok",
            "considered": len(recent),
            "dominant_focus": dominant,
            "themes": themes,
            "standing_directive": latest_goal_for[dominant],
        }

    def reset(self) -> None:
        with self._lock:
            self._insights.clear()
