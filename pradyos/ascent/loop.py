"""ASCENT — the autonomous self-improvement loop (the capstone orchestrator).

EVOLVE judges *one* hand-supplied candidate change; ASCENT is the layer above it
that makes the agent improve itself *unsupervised, end to end*. It answers the
two questions EVOLVE never does — **what should I improve, and what do I do with
the verdict?** — and closes the ouroboros loop:

  1. **Survey**   — run FORTIFY over the agent's own modules and rank them by
     robustness ``risk`` (the weakest module is the highest-value target).
  2. **Direct**   — synthesise a concrete improvement *directive* from the chosen
     module's single highest-severity finding (rule + line + remediation).
  3. **Propose**  — hand that directive to EVOLVE, which generates a candidate
     (local-LLM proposer) and gates it through FORTIFY + the REVIEW GATE into a
     verdict (``promote`` / ``revise`` / ``escalate`` / ``reject``).
  4. **Decide**   — map the verdict to an autonomous action and record it:

       * ``promote``  → **apply**    — queue the change for commit.
       * ``revise``   → **defer**    — safe but it worsened robustness; harden first.
       * ``escalate`` → **escalate** — touches a protected area → Sovereign.
       * ``reject``   → **discard**  — the gate denied it.

ASCENT's *core* is deterministic and side-effect-free: survey, directive
synthesis and the verdict→decision mapping are pure (FORTIFY parses, never runs;
the only non-determinism — the LLM proposer — lives inside the injected EVOLVE
engine, which tests replace with a fake). It never writes code or commits: a
``promote`` is *queued* for the Sovereign / an applier to commit, never applied
autonomously. It owns a private FORTIFY engine for surveying so target selection
never pollutes the live planes, and it degrades gracefully when no EVOLVE engine
(or proposer) is wired — it still identifies the target and the directive.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from pradyos.fortify import FortifyEngine

log = logging.getLogger("pradyos.ascent")

# verdict (from EVOLVE) → (autonomous decision, rationale). The single source of
# truth for what ASCENT does with a gated candidate.
_VERDICT_DECISION: dict[str, tuple[str, str]] = {
    "promote": ("apply", "safe and robustness held or improved — queued for apply"),
    "revise": ("defer", "safe to apply but robustness worsened — harden before applying"),
    "escalate": ("escalate", "touches a constitutionally protected area — Sovereign approval"),
    "reject": ("discard", "the review gate denied the change"),
}


class AscentError(RuntimeError):
    """Base class for ASCENT failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


@dataclass(frozen=True)
class Cycle:
    seq: int
    module: str
    directive: str
    verdict: str  # promote | revise | reject | escalate | skipped
    decision: str  # apply | defer | escalate | discard | skipped
    risk_before: int
    risk_after: int | None
    rationale: str
    evaluation: dict[str, Any] | None  # the full EVOLVE evaluation (None ⇒ not proposed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "module": self.module,
            "directive": self.directive,
            "verdict": self.verdict,
            "decision": self.decision,
            "risk_before": self.risk_before,
            "risk_after": self.risk_after,
            "rationale": self.rationale,
            "evaluation": self.evaluation,
        }


class AscentLoop:
    """Decide *what* to harden, drive EVOLVE's propose→gate, decide the outcome."""

    def __init__(self, evolve: Any | None = None, fortify: Any | None = None) -> None:
        # A PRIVATE FORTIFY engine for surveying — target selection must not
        # pollute the live FORTIFY plane's reports.
        self._fortify = fortify if fortify is not None else FortifyEngine()
        # The EVOLVE engine that proposes + gates candidates. Injected (shared
        # with the live plane) so cycles flow through the real local-LLM
        # proposer; tests inject a fake. None ⇒ survey/direct only.
        self._evolve = evolve
        self._cycles: list[Cycle] = []
        self._pending: list[dict[str, Any]] = []  # promoted changes queued for apply
        self._seq = 0
        self._lock = threading.RLock()

    # ── survey + direct (deterministic) ────────────────────────────────────────

    def survey(self, candidates: dict[str, str]) -> list[dict[str, Any]]:
        """Rank candidate modules by robustness risk; weakest (highest) first.

        ``candidates`` maps ``module_path → source``. Each entry carries its risk,
        finding counts, the single top finding, and the directive ASCENT would
        issue for it — so the survey alone answers "what should I improve next?".
        """
        self._validate_candidates(candidates)
        out: list[dict[str, Any]] = []
        for module, source in candidates.items():
            report = self._fortify.audit(module, source)
            top = report["findings"][0] if report["findings"] else None
            out.append(
                {
                    "module": module,
                    "risk": report["risk"],
                    "finding_count": report["finding_count"],
                    "by_severity": report["by_severity"],
                    "top_finding": top,
                    "directive": self._directive_for(top),
                }
            )
        # Deterministic order: highest risk first, ties broken by module name.
        out.sort(key=lambda e: (-e["risk"], e["module"]))
        return out

    @staticmethod
    def _directive_for(top: dict[str, Any] | None) -> str | None:
        if not top:
            return None
        return (
            f"Harden {top['rule']} at line {top['line']}: {top['remediation']}. "
            f"Issue: {top['message']}."
        )

    # ── the autonomous tick ────────────────────────────────────────────────────

    def run_cycle(self, candidates: dict[str, str], max_targets: int = 1) -> list[dict[str, Any]]:
        """Survey → direct → propose → decide → record for the weakest module(s).

        Targets the ``max_targets`` modules with the highest risk *that have
        findings*. Each becomes one recorded :class:`Cycle`. Returns the cycles
        created (most-recent last). With no EVOLVE engine (or no proposer) wired,
        each cycle is recorded as ``skipped`` but still names its target + directive.
        """
        # bool is an int subclass — reject it so JSON ``true`` isn't read as 1.
        if isinstance(max_targets, bool) or not isinstance(max_targets, int) or max_targets <= 0:
            raise AscentError("max_targets must be a positive integer")
        ranked = self.survey(candidates)  # validates candidates
        targets = [e for e in ranked if e["finding_count"] > 0][:max_targets]

        results: list[dict[str, Any]] = []
        for tgt in targets:
            module = tgt["module"]
            directive = tgt["directive"]
            risk_before = tgt["risk"]
            verdict = "skipped"
            risk_after: int | None = None
            evaluation: dict[str, Any] | None = None
            after_source: str | None = None
            note = ""

            if self._evolve is None:
                note = "no EVOLVE engine wired — target identified only"
            else:
                # propose() may call a (blocking) local LLM; ASCENT is sync, the
                # web surface runs run_cycle off the event loop. A raising/dead
                # proposer must NOT crash the loop — degrade to a recorded skip
                # (log details server-side; keep the cycle note generic).
                try:
                    res = self._evolve.propose(module, directive, before=candidates[module])
                except Exception as exc:  # noqa: BLE001 — a raising proposer must not crash the loop
                    log.warning("ascent: evolve.propose failed for %s: %s", module, exc)
                    res = {"proposed": False, "note": "evolve proposer failed"}
                if res.get("proposed"):
                    evaluation = res.get("evaluation") or {}
                    verdict = evaluation.get("verdict", "skipped")
                    risk_after = evaluation.get("risk_after")
                    after_source = res.get("after")
                else:
                    note = res.get("note") or "proposer produced no candidate"

            decision, rationale = self._decide(verdict, note)
            # Record + (if promoted) enqueue under ONE lock so a concurrent
            # reset() cannot interleave and orphan a pending entry.
            cycle = self._record(
                module,
                directive,
                verdict,
                decision,
                risk_before,
                risk_after,
                rationale,
                evaluation,
                after_source,
            )
            results.append(cycle.to_dict())
        return results

    @staticmethod
    def _decide(verdict: str, note: str) -> tuple[str, str]:
        if verdict in _VERDICT_DECISION:
            return _VERDICT_DECISION[verdict]
        return "skipped", note or "no candidate was evaluated"

    def _record(
        self,
        module: str,
        directive: str,
        verdict: str,
        decision: str,
        risk_before: int,
        risk_after: int | None,
        rationale: str,
        evaluation: dict[str, Any] | None,
        after_source: str | None,
    ) -> Cycle:
        with self._lock:
            self._seq += 1
            cycle = Cycle(
                seq=self._seq,
                module=module,
                directive=directive,
                verdict=verdict,
                decision=decision,
                risk_before=risk_before,
                risk_after=risk_after,
                rationale=rationale,
                evaluation=evaluation,
            )
            self._cycles.append(cycle)
            # Enqueue the promoted change in the SAME lock section so the cycle
            # and its pending entry can never be split by a concurrent reset().
            if decision == "apply":
                self._pending.append(
                    {
                        "seq": cycle.seq,
                        "module": cycle.module,
                        "directive": cycle.directive,
                        "risk_before": cycle.risk_before,
                        "risk_after": cycle.risk_after,
                        "after": after_source,
                    }
                )
            return cycle

    # ── introspection ──────────────────────────────────────────────────────────

    def cycle(self, seq: int) -> dict[str, Any]:
        with self._lock:
            for c in self._cycles:
                if c.seq == seq:
                    return c.to_dict()
        raise AscentError(f"unknown cycle seq={seq}")

    def cycles(self, limit: int = 20) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit <= 0:
            raise AscentError("limit must be a positive integer")
        with self._lock:
            return [c.to_dict() for c in self._cycles[-limit:]]

    def pending(self, limit: int = 20) -> list[dict[str, Any]]:
        """The promoted changes queued for apply (never applied autonomously)."""
        if not isinstance(limit, int) or limit <= 0:
            raise AscentError("limit must be a positive integer")
        with self._lock:
            return [dict(p) for p in self._pending[-limit:]]

    def stats(self) -> dict[str, Any]:
        proposer_configured = False
        if self._evolve is not None:
            try:
                proposer_configured = bool(self._evolve.stats().get("proposer_configured"))
            except Exception:
                proposer_configured = False
        with self._lock:
            by_verdict: dict[str, int] = {}
            by_decision: dict[str, int] = {}
            for c in self._cycles:
                by_verdict[c.verdict] = by_verdict.get(c.verdict, 0) + 1
                by_decision[c.decision] = by_decision.get(c.decision, 0) + 1
            return {
                "cycles": len(self._cycles),
                "by_verdict": by_verdict,
                "by_decision": by_decision,
                "pending": len(self._pending),
                "evolve_wired": self._evolve is not None,
                "proposer_configured": proposer_configured,
            }

    @staticmethod
    def _validate_candidates(candidates: dict[str, str]) -> None:
        if not isinstance(candidates, dict) or not candidates:
            raise AscentError("candidates must be a non-empty mapping of module path → source")
        for module, source in candidates.items():
            if not _is_str(module):
                raise AscentError("candidate module paths must be non-empty strings")
            if not isinstance(source, str):
                raise AscentError("candidate source must be a string")

    def reset(self) -> None:
        with self._lock:
            self._cycles.clear()
            self._pending.clear()
            self._seq = 0
            self._fortify.reset()
