"""CRITIC — an adversarial critic ensemble (autonomy L4).

The REVIEW gate (`pradyos/review`) enforces hard *rules* on a code change (e.g.
"don't silently delete tests"). The CRITIC ensemble is the complementary *judgment*
layer: several independent critics, each skeptical and each looking at a different
**dimension** (safety / correctness / value), score a proposal 0..1 and may raise
a **blocker**. The ensemble aggregates them into one verdict used to gate action —
so a self-edit, or a goal about to run, is vetted from several angles before the
Sovereign's apply-gate, not just one.

Default critics are deterministic (transparent, testable, offline). A blocker from
*any* critic rejects outright (safety is a veto, not an average); otherwise the
mean score must clear a threshold. Critics are pluggable, so an LLM-backed critic
can be added without touching callers.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

__all__ = ["Critique", "Critic", "CriticEnsemble", "default_critics"]

# Patterns that are dangerous enough to VETO a proposal outright (a blocker).
_DANGER = [
    r"rm\s+-rf", r"mkfs", r"dd\s+if=", r":\(\)\s*\{", r"\bdrop\s+table\b",
    r"\bdelete\s+from\b", r"format\s+[a-z]:", r"\bshutdown\b", r"\breboot\b",
    r"disable\s+(the\s+)?(security|firewall|auth|sandbox)", r"bypass\s+(auth|security|the\s+gate)",
    r"exfiltrat", r"(send|upload|leak|post)\s+.*(password|secret|api[_\s-]?key|private\s+key|token)",
    r"curl\s+[^|]*\|\s*(sh|bash)", r"wget\s+[^|]*\|\s*(sh|bash)", r"chmod\s+777\s+/",
    r"lock\s+the\s+(machine|computer|user'?s?\s+machine)", r"brick\s+the",
]
# Soft signals (no veto, just score nudges).
_BAD = [r"\btodo\b", r"\bfixme\b", r"\bhack\b", r"\bxxx\b", r"skip\s+test", r"delete\s+test",
        r"# *stub", r"pass\s*# *stub", r"hardcode", r"disable\s+test"]
_GOOD = [r"\btest", r"\bassert", r"\bverify", r"\bvalidate", r"docstring", r"type[\s-]?hint",
         r"\brollback", r"\bidempotent", r"\bguard"]


@dataclass(frozen=True)
class Critique:
    critic: str
    dimension: str
    score: float          # 0..1
    is_blocker: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "critic": self.critic,
            "dimension": self.dimension,
            "score": round(self.score, 4),
            "is_blocker": self.is_blocker,
            "reason": self.reason,
        }


@dataclass
class Critic:
    """A named, single-dimension scorer. ``fn(proposal) -> Critique``."""

    name: str
    dimension: str
    fn: Callable[[str], Critique]

    def score(self, proposal: str) -> Critique:
        return self.fn(proposal)


def _count(patterns: list[str], text: str) -> list[str]:
    hits: list[str] = []
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            hits.append(p)
    return hits


def _safety_critic(proposal: str) -> Critique:
    danger = _count(_DANGER, proposal)
    if danger:
        return Critique(
            "safety", "safety", 0.0, True,
            f"dangerous/destructive pattern(s): {', '.join(danger[:3])}",
        )
    return Critique("safety", "safety", 1.0, False, "no destructive patterns found")


def _correctness_critic(proposal: str) -> Critique:
    bad = _count(_BAD, proposal)
    good = _count(_GOOD, proposal)
    score = max(0.0, min(1.0, 0.6 + 0.1 * len(good) - 0.2 * len(bad)))
    reason = []
    if good:
        reason.append(f"+{len(good)} quality signal(s)")
    if bad:
        reason.append(f"-{len(bad)} smell(s)")
    return Critique("correctness", "correctness", score, False, "; ".join(reason) or "neutral")


def _value_critic(proposal: str) -> Critique:
    words = len(proposal.split())
    if words < 2:
        return Critique("value", "value", 0.2, False, "too vague to assess value")
    score = min(1.0, 0.45 + min(0.5, words / 60))
    return Critique("value", "value", score, False, f"{words}-token proposal with clear intent")


def default_critics() -> list[Critic]:
    """The skeptical default panel: safety (veto), correctness, value."""
    return [
        Critic("safety", "safety", _safety_critic),
        Critic("correctness", "correctness", _correctness_critic),
        Critic("value", "value", _value_critic),
    ]


class CriticEnsemble:
    """Runs the panel and aggregates a single gating verdict."""

    def __init__(self, critics: list[Critic] | None = None, threshold: float = 0.5) -> None:
        self._critics = critics if critics is not None else default_critics()
        self._threshold = float(threshold)
        self._judged = 0
        self._approved = 0
        self._lock = threading.RLock()

    def critics(self) -> list[dict[str, str]]:
        return [{"name": c.name, "dimension": c.dimension} for c in self._critics]

    def judge(self, proposal: str) -> dict[str, Any]:
        """Score a proposal from every angle; reject on any blocker or low mean."""
        if not isinstance(proposal, str):
            proposal = str(proposal or "")
        critiques = [c.score(proposal) for c in self._critics]
        blockers = [q.to_dict() for q in critiques if q.is_blocker]
        mean = sum(q.score for q in critiques) / len(critiques) if critiques else 0.0
        approved = (not blockers) and mean >= self._threshold
        with self._lock:
            self._judged += 1
            if approved:
                self._approved += 1
        return {
            "verdict": "approve" if approved else "reject",
            "score": round(mean, 4),
            "threshold": self._threshold,
            "blockers": blockers,
            "critiques": [q.to_dict() for q in critiques],
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "judged": self._judged,
                "approved": self._approved,
                "rejected": self._judged - self._approved,
                "critics": [c.name for c in self._critics],
                "threshold": self._threshold,
            }
