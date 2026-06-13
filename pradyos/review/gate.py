"""REVIEW GATE — vet a self-modification before it is committed.

The capstone of safe self-improvement. Before the machine changes its own code
(NIGHT CITADEL / HELIOS FORGE), the proposed change is run through a panel of
independent, deterministic **lenses** — the ouroboros "review before you commit
to yourself" pattern, made reproducible (no LLM, no I/O, parses-not-executes):

  * ``parse``            — the new source must still parse (no broken commits).
  * ``api_preservation`` — public top-level symbols present *before* must still
    exist *after* (no silent breaking of the public surface).
  * ``test_retention``   — a change must not quietly delete ``def test_*`` cases.
  * ``forbidden_path``   — touching the constitution / audit ledger / security
    kernel is never autonomous; it must cross the Sovereign boundary (escalate).
  * ``change_size``      — very large diffs are flagged for extra scrutiny.

The panel composes into one gated decision:

  * any hard lens fails           → **deny**
  * touches a forbidden path      → **escalate** (Sovereign approval required)
  * only soft warnings            → **revise**
  * clean                         → **approve**

Deterministic and side-effect-free, so it slots into the constellation and is
tested against hand-computed ground truth.
"""

from __future__ import annotations

import ast
import threading
from dataclasses import dataclass
from typing import Any

# Constitutionally protected areas — a self-modification here may never run
# autonomously; it must be escalated to the Sovereign (cf. BASTION / IMPERIUM).
_FORBIDDEN_SUBSTRINGS = (
    "constitution",
    "core/audit",
    "audit_log",
    "imperium/kernel",
    "imperium/policy",
    "bastion",
    "review/gate",  # the gate must not autonomously rewrite itself
)

_BIG_CHANGE_LINES = 400


class ReviewError(RuntimeError):
    """Base class for REVIEW GATE failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _public_symbols(source: str) -> set[str]:
    """Top-level functions/classes not prefixed with ``_`` (the public surface)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if not node.name.startswith("_"):
                out.add(node.name)
    return out


def _test_funcs(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        n.name
        for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test_")
    }


@dataclass(frozen=True)
class LensResult:
    name: str
    verdict: str  # pass | warn | fail
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "verdict": self.verdict, "reason": self.reason}


@dataclass(frozen=True)
class Review:
    seq: int
    path: str
    decision: str  # approve | revise | deny | escalate
    lenses: tuple[LensResult, ...]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "path": self.path,
            "decision": self.decision,
            "lenses": [lens.to_dict() for lens in self.lenses],
            "summary": self.summary,
        }


class ReviewGate:
    """Runs the deterministic review panel over proposed self-modifications."""

    def __init__(self) -> None:
        self._reviews: list[Review] = []
        self._seq = 0
        self._lock = threading.RLock()

    # ── the panel ─────────────────────────────────────────────────────────────

    def assess(self, path: str, after: str, before: str = "") -> dict[str, Any]:
        """Review a proposed change to ``path`` (``before`` empty ⇒ new file)."""
        if not _is_str(path):
            raise ReviewError("path must be a non-empty string")
        if not isinstance(after, str):
            raise ReviewError("after must be a string")
        if not isinstance(before, str):
            raise ReviewError("before must be a string")

        lenses = [
            self._lens_parse(after),
            self._lens_api(before, after),
            self._lens_tests(path, before, after),
            self._lens_forbidden(path),
            self._lens_size(before, after),
        ]
        decision, summary = self._decide(lenses)
        with self._lock:
            self._seq += 1
            review = Review(self._seq, path, decision, tuple(lenses), summary)
            self._reviews.append(review)
        return review.to_dict()

    @staticmethod
    def _lens_parse(after: str) -> LensResult:
        try:
            ast.parse(after)
        except SyntaxError as exc:
            return LensResult("parse", "fail", f"new source does not parse: {exc}")
        return LensResult("parse", "pass", "new source parses cleanly")

    @staticmethod
    def _lens_api(before: str, after: str) -> LensResult:
        if not before.strip():
            return LensResult("api_preservation", "pass", "new file — no prior public surface")
        removed = sorted(_public_symbols(before) - _public_symbols(after))
        if removed:
            return LensResult("api_preservation", "fail", f"public symbols removed: {removed}")
        return LensResult("api_preservation", "pass", "public surface preserved")

    @staticmethod
    def _lens_tests(path: str, before: str, after: str) -> LensResult:
        if "test" not in path.lower():
            return LensResult("test_retention", "pass", "not a test file")
        removed = sorted(_test_funcs(before) - _test_funcs(after))
        if removed:
            return LensResult("test_retention", "fail", f"test cases removed: {removed}")
        return LensResult("test_retention", "pass", "no test cases removed")

    @staticmethod
    def _lens_forbidden(path: str) -> LensResult:
        low = path.lower()
        for sub in _FORBIDDEN_SUBSTRINGS:
            if sub in low:
                return LensResult(
                    "forbidden_path", "warn", f"touches protected area ({sub}) — Sovereign approval"
                )
        return LensResult("forbidden_path", "pass", "no protected path touched")

    @staticmethod
    def _lens_size(before: str, after: str) -> LensResult:
        net = after.count("\n") - before.count("\n")
        if net > _BIG_CHANGE_LINES:
            return LensResult(
                "change_size", "warn", f"large change (+{net} lines) — review closely"
            )
        return LensResult("change_size", "pass", f"change size ok (net {net:+d} lines)")

    @staticmethod
    def _decide(lenses: list[LensResult]) -> tuple[str, str]:
        by_name = {lens.name: lens for lens in lenses}
        hard = [
            lens
            for lens in lenses
            if lens.verdict == "fail"
            and lens.name in ("parse", "api_preservation", "test_retention")
        ]
        if hard:
            return "deny", "; ".join(f"{lens.name}: {lens.reason}" for lens in hard)
        if by_name["forbidden_path"].verdict == "warn":
            return "escalate", by_name["forbidden_path"].reason
        warns = [lens for lens in lenses if lens.verdict == "warn"]
        if warns:
            return "revise", "; ".join(f"{lens.name}: {lens.reason}" for lens in warns)
        return "approve", "all lenses passed"

    # ── introspection ────────────────────────────────────────────────────────

    def review(self, seq: int) -> dict[str, Any]:
        with self._lock:
            for r in self._reviews:
                if r.seq == seq:
                    return r.to_dict()
        raise ReviewError(f"unknown review seq={seq}")

    def reviews(self, limit: int = 20) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit <= 0:
            raise ReviewError("limit must be a positive integer")
        with self._lock:
            return [r.to_dict() for r in self._reviews[-limit:]]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_decision: dict[str, int] = {}
            for r in self._reviews:
                by_decision[r.decision] = by_decision.get(r.decision, 0) + 1
            return {"reviews": len(self._reviews), "by_decision": by_decision}

    def reset(self) -> None:
        with self._lock:
            self._reviews.clear()
            self._seq = 0
