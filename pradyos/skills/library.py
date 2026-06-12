"""SKILL LIBRARY — learn reusable skills from experience (self-improvement).

The agent gets better over time by distilling successful task experiences into
named, reusable **skills**, then recalling and reinforcing them:

  * ``learn`` registers a skill — a trigger (the kind of intent it applies to)
    plus the ordered steps that worked.
  * ``match`` ranks the library against a new intent by trigger-term overlap
    weighted by the skill's **proven confidence**, so battle-tested skills win.
  * ``reinforce`` updates a skill's success/failure tally from real outcomes;
    confidence is a Laplace-smoothed success ratio (prior 0.5, honest about
    skills with little evidence).
  * ``prune`` retires skills that keep failing — the library heals itself.

The whole core is pure and deterministic (no LLM, no I/O), so it slots into the
constellation the same way every other plane does and is unit-tested against
hand-computed ground truth. An LLM can later author the ``steps`` of a skill,
but selection, reinforcement, and pruning are deterministic policy.
"""

from __future__ import annotations

import re
import threading
from typing import Any

_WORD = re.compile(r"[a-z0-9]+")


class SkillError(RuntimeError):
    """Base class for SKILL LIBRARY failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _terms(text: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(text.lower()) if len(w) > 1)


def _as_terms(trigger: Any) -> frozenset[str]:
    """Accept a trigger phrase (str) or an explicit list of keywords."""
    if isinstance(trigger, str):
        terms = _terms(trigger)
    elif isinstance(trigger, list | tuple | set | frozenset):
        if not all(isinstance(t, str) for t in trigger):
            raise SkillError("trigger keywords must be strings")
        terms = frozenset(t.lower() for t in trigger if _is_str(t) and len(t) > 1)
    else:
        raise SkillError("trigger must be a string or a list of keyword strings")
    if not terms:
        raise SkillError("trigger must yield at least one keyword")
    return terms


def _as_steps(steps: Any) -> tuple[str, ...]:
    if not isinstance(steps, list | tuple) or not steps:
        raise SkillError("steps must be a non-empty list of strings")
    if not all(_is_str(s) for s in steps):
        raise SkillError("each step must be a non-empty string")
    return tuple(str(s) for s in steps)


class _Skill:
    __slots__ = (
        "id",
        "name",
        "trigger",
        "steps",
        "preconditions",
        "success",
        "failure",
        "version",
        "examples",
        "seq",
    )

    def __init__(
        self,
        skill_id: str,
        name: str,
        trigger: frozenset[str],
        steps: tuple[str, ...],
        preconditions: tuple[str, ...],
        seq: int,
    ) -> None:
        self.id = skill_id
        self.name = name
        self.trigger = trigger
        self.steps = steps
        self.preconditions = preconditions
        self.success = 0
        self.failure = 0
        self.version = 1
        self.examples: list[str] = []
        self.seq = seq

    @property
    def attempts(self) -> int:
        return self.success + self.failure

    @property
    def confidence(self) -> float:
        # Laplace smoothing: prior 0.5, converges to the true success rate.
        return round((self.success + 1) / (self.attempts + 2), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "trigger": sorted(self.trigger),
            "steps": list(self.steps),
            "preconditions": list(self.preconditions),
            "success": self.success,
            "failure": self.failure,
            "attempts": self.attempts,
            "confidence": self.confidence,
            "version": self.version,
            "examples": list(self.examples),
        }


class SkillLibrary:
    """A self-improving store of reusable skills distilled from experience."""

    def __init__(self) -> None:
        self._skills: dict[str, _Skill] = {}
        self._seq = 0
        self._lock = threading.RLock()

    # ── learn / revise ────────────────────────────────────────────────────────

    def learn(
        self,
        skill_id: str,
        name: str,
        trigger: Any,
        steps: Any,
        preconditions: Any = (),
        example: str | None = None,
    ) -> dict[str, Any]:
        """Register a new skill distilled from a successful experience."""
        if not _is_str(skill_id):
            raise SkillError("skill_id must be a non-empty string")
        if not _is_str(name):
            raise SkillError("name must be a non-empty string")
        trig = _as_terms(trigger)
        step_t = _as_steps(steps)
        if isinstance(preconditions, str):
            raise SkillError("preconditions must be a list of strings, not a string")
        if not isinstance(preconditions, list | tuple) or not all(
            _is_str(p) for p in preconditions
        ):
            raise SkillError("preconditions must be a list of non-empty strings")
        with self._lock:
            if skill_id in self._skills:
                raise SkillError(f"skill {skill_id!r} already exists (use revise/reinforce)")
            self._seq += 1
            sk = _Skill(skill_id, name, trig, step_t, tuple(preconditions), self._seq)
            if example is not None and _is_str(example):
                sk.examples.append(example)
            self._skills[skill_id] = sk
            return sk.to_dict()

    def revise(self, skill_id: str, steps: Any) -> dict[str, Any]:
        """Replace a skill's steps and bump its version (it learned a better way)."""
        step_t = _as_steps(steps)
        with self._lock:
            sk = self._require(skill_id)
            sk.steps = step_t
            sk.version += 1
            return sk.to_dict()

    # ── reinforce / prune (self-improvement) ─────────────────────────────────

    def reinforce(self, skill_id: str, success: bool, example: str | None = None) -> dict[str, Any]:
        """Record a real outcome for a skill, updating its proven confidence."""
        if not isinstance(success, bool):
            raise SkillError("success must be a boolean")
        with self._lock:
            sk = self._require(skill_id)
            if success:
                sk.success += 1
                if example is not None and _is_str(example) and example not in sk.examples:
                    sk.examples.append(example)
            else:
                sk.failure += 1
            return sk.to_dict()

    def prune(self, min_confidence: float = 0.34, min_attempts: int = 3) -> list[str]:
        """Retire skills that keep failing (self-healing of the skill set)."""
        if not isinstance(min_attempts, int) or min_attempts < 1:
            raise SkillError("min_attempts must be a positive integer")
        with self._lock:
            doomed = [
                sid
                for sid, sk in self._skills.items()
                if sk.attempts >= min_attempts and sk.confidence < min_confidence
            ]
            for sid in doomed:
                del self._skills[sid]
            return sorted(doomed)

    # ── match / recall ────────────────────────────────────────────────────────

    def match(self, intent: str, limit: int = 5) -> list[dict[str, Any]]:
        """Rank applicable skills for an intent (overlap × proven confidence)."""
        if not _is_str(intent):
            raise SkillError("intent must be a non-empty string")
        if not isinstance(limit, int) or limit <= 0:
            raise SkillError("limit must be a positive integer")
        want = _terms(intent)
        with self._lock:
            scored: list[tuple[int, float, str, dict[str, Any]]] = []
            for sk in self._skills.values():
                matched = want & sk.trigger
                if not matched:
                    continue
                d = sk.to_dict()
                d["match_overlap"] = len(matched)
                d["matched_terms"] = sorted(matched)
                # Deterministic rank: more overlap, then higher proven confidence.
                scored.append((-len(matched), -sk.confidence, sk.id, d))
        scored.sort(key=lambda t: (t[0], t[1], t[2]))
        return [d for _, _, _, d in scored[:limit]]

    def recall(self, skill_id: str) -> dict[str, Any]:
        with self._lock:
            return self._require(skill_id).to_dict()

    def skills(self) -> list[dict[str, Any]]:
        with self._lock:
            return [sk.to_dict() for sk in sorted(self._skills.values(), key=lambda s: s.seq)]

    # ── introspection ────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            n = len(self._skills)
            proven = sum(1 for sk in self._skills.values() if sk.success > 0)
            total_attempts = sum(sk.attempts for sk in self._skills.values())
            return {"skills": n, "proven": proven, "total_attempts": total_attempts}

    def reset(self) -> None:
        with self._lock:
            self._skills.clear()
            self._seq = 0

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, skill_id: str) -> _Skill:
        sk = self._skills.get(skill_id)
        if sk is None:
            raise SkillError(f"unknown skill {skill_id!r}")
        return sk
