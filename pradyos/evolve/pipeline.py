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

import logging
import threading
from dataclasses import dataclass
from typing import Any

from pradyos.fortify import FortifyEngine
from pradyos.review import ReviewGate

log = logging.getLogger("pradyos.evolve")


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

    def __init__(self, proposer: Any | None = None) -> None:
        # Private engines: evaluating a candidate must not pollute the live planes.
        self._fortify = FortifyEngine()
        self._review = ReviewGate()
        # Optional code proposer: callable(before, directive) -> after source.
        # The live wiring uses a LOCAL LLM (Ollama → no API credits); tests inject
        # a fake. None ⇒ EVOLVE only judges externally-supplied changes.
        self._proposer = proposer
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

    def propose(self, path: str, directive: str, before: str = "") -> dict[str, Any]:
        """Generate a candidate change with the proposer, then judge it.

        Turns the judge into a doer: the (local-LLM) proposer writes a candidate
        ``after`` for ``directive``; EVOLVE then runs its full gate on it. The
        change is never applied — it is *judged*, gated, and returned. Degrades
        gracefully (``proposed: false`` + a note) when no proposer is configured
        or the proposer is unavailable.
        """
        if not _is_str(path):
            raise EvolveError("path must be a non-empty string")
        if not _is_str(directive):
            raise EvolveError("directive must be a non-empty string")
        if not isinstance(before, str):
            raise EvolveError("before must be a string")

        base = {
            "path": path,
            "directive": directive,
            "proposed": False,
            "after": None,
            "evaluation": None,
        }
        if self._proposer is None:
            return {**base, "note": "no code proposer configured"}
        try:
            after = self._proposer(before, directive)
        except Exception as exc:  # noqa: BLE001 — a dead/absent LLM must not crash the plane
            # Log internally; keep the client-facing note generic (no transport leak).
            log.warning("evolve proposer failed for %s: %s", path, exc)
            return {**base, "note": "proposer unavailable"}
        if not isinstance(after, str) or not after.strip():
            return {**base, "note": "proposer returned no code"}

        evaluation = self.evaluate(path, after, before)
        return {
            "path": path,
            "directive": directive,
            "proposed": True,
            "after": after,
            "evaluation": evaluation,
            "note": f"verdict={evaluation['verdict']}",
        }

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
            return {
                "evaluations": len(self._evals),
                "by_verdict": by_verdict,
                "proposer_configured": self._proposer is not None,
            }

    def reset(self) -> None:
        with self._lock:
            self._evals.clear()
            self._seq = 0
            self._fortify.reset()
            self._review.reset()


def _strip_code_fences(text: str) -> str:
    """Pull Python out of a ```python ... ``` block if the model wrapped it."""
    import re

    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return (m.group(1) if m else text).strip() + "\n"


class OllamaProposer:
    """A code proposer backed by a LOCAL Ollama model — zero API credits.

    Constructed lazily and never contacted at import time. If Ollama is not
    running, ``__call__`` raises and :meth:`EvolveEngine.propose` degrades
    gracefully. Used as the live proposer in production; tests inject a fake.
    """

    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def __call__(self, before: str, directive: str) -> str:
        import json
        import urllib.request

        prompt = (
            "You are refactoring a single Python module. "
            f"{directive}\n"
            "Return ONLY the complete revised module as Python code — no prose, "
            "no explanation. Preserve every public function/class name.\n\n"
            f"{before}"
        )
        payload = json.dumps({"model": self.model, "prompt": prompt, "stream": False}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return _strip_code_fences(data.get("response", ""))
