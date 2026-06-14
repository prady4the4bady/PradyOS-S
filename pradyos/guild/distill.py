"""Auto-distillation — turn a completed Guild project into a reusable skill (L1).

When the Guild finishes an objective, :func:`distill_project` writes it into the
skill library (a new objective becomes a new skill; a repeat objective reinforces
the existing one). This is the accumulation-of-competence half of the autonomy
loop: solved work becomes a retrievable, success-weighted skill the OS can reuse.

Best-effort and decoupled — it takes the skill library as an argument and never
raises, so a distillation hiccup can never sink a Guild run.
"""

from __future__ import annotations

import re
from typing import Any


def skill_id_for(objective: str) -> str:
    """Deterministic skill id derived from an objective."""
    slug = re.sub(r"[^a-z0-9]+", "-", objective.lower()).strip("-")[:48]
    return "guild-" + (slug or "skill")


def distill_project(skills_lib: Any, project: dict[str, Any]) -> str | None:
    """Distil a completed project into the skill library. Returns the skill id
    (new or reinforced) or ``None`` if there was nothing to learn."""
    objective = str((project or {}).get("objective", "")).strip()
    if not objective:
        return None
    sid = skill_id_for(objective)
    synthesis = str(project.get("synthesis", "") or "")
    steps = [s.strip() for s in synthesis.splitlines() if s.strip()][:8]
    if not steps:
        steps = [f"Apply the Guild's approach to: {objective[:140]}"]
    try:
        skills_lib.learn(sid, objective[:60], objective, steps)
        return sid
    except Exception:  # noqa: BLE001 — already exists (repeat objective) ⇒ reinforce it
        try:
            skills_lib.reinforce(sid, True)
            return sid
        except Exception:  # noqa: BLE001
            return None
