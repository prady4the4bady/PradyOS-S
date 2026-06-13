"""EVOLVE — the autonomous self-improvement pipeline.

The capstone that makes the agent improve *itself* safely, end to end, instead
of exposing five separate endpoints. Given a proposed change to one of its own
modules (``before`` → ``after``), EVOLVE composes the existing planes into one
gated decision:

  1. FORTIFY audits the robustness of the code **before** and **after** the
     change → a risk delta (did the change reduce or add weaknesses?).
  2. The REVIEW GATE vets the change for safety (parse, public-API and test
     preservation, forbidden paths, size).
  3. The two are composed into a single **verdict**:

       * ``reject``   — the review gate denied it (broken / breaks the surface).
       * ``escalate`` — it touches a constitutionally protected area → Sovereign.
       * ``revise``   — safe to apply, but it *adds* robustness weaknesses.
       * ``promote``  — safe **and** robustness held or improved → apply it.

Pure, deterministic, parses-not-executes: EVOLVE owns private FORTIFY and
REVIEW engines, so evaluating a candidate has no side effects on the live planes
and is unit-tested against hand-computed verdicts. It never writes code itself —
it *judges* a proposed change; generating the change is a separate (LLM) step
that this pipeline gates.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from pradyos.fortify import FortifyEngine
from pradyos.review import ReviewGate


class EvolveError(RuntimeError):
    """Base class for EVOLVE failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


@dataclass(frozen=True)
class Evaluation:
    seq: int
    path: str
    verdict: str  # promote | revise | reject | escalate
    risk_before: int
    risk_after: int
    risk_delta: int
    review_decision: str
    rationale: str
    review: dict[str, Any]
    fortify_after: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "path": self.path,
            "verdict": self.verdict,
            "risk_before": self.risk_before,
            "risk_after": self.risk_after,
            "risk_delta": self.risk_delta,
            "review_decision": self.review_decision,
            "rationale": self.rationale,
            "review": self.review,
            "fortify_after": self.fortify_after,
        }


class EvolveEngine:
    """Composes FORTIFY + REVIEW GATE into a gated self-improvement decision."""

    def __init__(self) -> None:
        # Private engines: evaluating a candidate must not pollute the live planes.
        self._fortify = FortifyEngine()
        self._review = ReviewGate()
        self._evals: list[Evaluation] = []
        self._seq = 0
        self._lock = threading.RLock()

    def evaluate(self, path: str, after: str, before: str = "") -> dict[str, Any]:
        """Judge a proposed self-modification to ``path`` and record the verdict."""
        if not _is_str(path):
            raise EvolveError("path must be a non-empty string")
        if not isinstance(after, str):
            raise EvolveError("after must be a string")
        if not isinstance(before, str):
            raise EvolveError("before must be a string")

        risk_before = self._fortify.audit(path, before)["risk"] if before.strip() else 0
        fortify_after = self._fortify.audit(path, after)
        risk_after = fortify_after["risk"]
        review = self._review.assess(path, after, before)
        decision = review["decision"]

        verdict, rationale = self._compose(decision, risk_before, risk_after, review["summary"])

        with self._lock:
            self._seq += 1
            ev = Evaluation(
                seq=self._seq,
                path=path,
                verdict=verdict,
                risk_before=risk_before,
                risk_after=risk_after,
                risk_delta=risk_after - risk_before,
                review_decision=decision,
                rationale=rationale,
                review=review,
                fortify_after=fortify_after,
            )
            self._evals.append(ev)
        return ev.to_dict()

    @staticmethod
    def _compose(
        decision: str, risk_before: int, risk_after: int, review_summary: str
    ) -> tuple[str, str]:
        if decision == "deny":
            return "reject", f"review gate denied the change ({review_summary})"
        if decision == "escalate":
            return "escalate", f"change requires Sovereign approval ({review_summary})"
        # review approved or only needs cosmetic revision — decide on robustness.
        if risk_after > risk_before:
            return (
                "revise",
                f"safe to apply but robustness worsened (risk {risk_before} → {risk_after}); harden first",
            )
        if risk_after < risk_before:
            return "promote", f"safe and robustness improved (risk {risk_before} → {risk_after})"
        return "promote", f"safe and robustness held (risk {risk_before} → {risk_after})"

    # ── introspection ────────────────────────────────────────────────────────

    def evaluation(self, seq: int) -> dict[str, Any]:
        with self._lock:
            for ev in self._evals:
                if ev.seq == seq:
                    return ev.to_dict()
        raise EvolveError(f"unknown evaluation seq={seq}")

    def evaluations(self, limit: int = 20) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit <= 0:
            raise EvolveError("limit must be a positive integer")
        with self._lock:
            return [ev.to_dict() for ev in self._evals[-limit:]]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_verdict: dict[str, int] = {}
            for ev in self._evals:
                by_verdict[ev.verdict] = by_verdict.get(ev.verdict, 0) + 1
            return {"evaluations": len(self._evals), "by_verdict": by_verdict}

    def reset(self) -> None:
        with self._lock:
            self._evals.clear()
            self._seq = 0
            self._fortify.reset()
            self._review.reset()
