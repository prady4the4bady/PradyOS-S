"""IMPERIUM Policy Engine — Phase 14.

Sovereign-configurable policy enforcement at dispatch time.

The PolicyEngine is *pure* — no bus, no kernel imports, no external deps.
It is injected into ImperiumKernel and consulted before every task dispatch.

Rule types
----------
constitutional_guard
    Blocks matching tasks unconditionally with a configured deny_reason.

rate_limit
    Blocks matching tasks when more than ``max_per_minute`` tasks of that
    description have been dispatched within ``window_seconds`` (default 60).
    Counter state lives in a plain list of float timestamps pruned lazily.

approval_required
    Marks the task as requiring approval (allowed=True returned — enforcement
    of *who* approves is delegated to the Sovereign layer, not this engine).

Match semantics
---------------
A rule fires when every key/value in its ``match`` dict is present in
``task.metadata``.  String comparisons use substring matching (value is
*contained in* the metadata value).  An empty ``match`` dict matches every
task.

Thread safety
-------------
All mutable state is protected by a single ``threading.Lock``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Sentinel / error type (imported by imperium.py)
# ---------------------------------------------------------------------------

class PolicyViolationError(Exception):
    """Raised by ImperiumKernel when a task is blocked by the PolicyEngine."""


# ---------------------------------------------------------------------------
# Verdict dataclass
# ---------------------------------------------------------------------------

@dataclass
class PolicyVerdict:
    allowed: bool
    reason: str  # "ok" when allowed; human-readable denial reason when blocked

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason}


# ---------------------------------------------------------------------------
# PolicyEngine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """Evaluate ImperiumTasks against a loaded ruleset.

    Parameters
    ----------
    config:
        Optional configuration dict (reserved for future use).
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._rules: list[dict[str, Any]] = []
        # rate-limit counters: rule_index -> list of float timestamps
        self._rate_counters: dict[int, list[float]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def load(self, rules: list[dict[str, Any]]) -> None:
        """Replace the active ruleset with *rules*.

        Clears all rate-limit counters — a fresh ruleset starts with a
        fresh slate.
        """
        with self._lock:
            self._rules = list(rules)
            self._rate_counters = {}

    def get_rules(self) -> list[dict[str, Any]]:
        """Return a *copy* of the current ruleset (mutation-safe)."""
        with self._lock:
            return [dict(r) for r in self._rules]

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, task: Any) -> PolicyVerdict:
        """Check *task* against the current ruleset.

        Returns :class:`PolicyVerdict` with ``allowed=True`` when no rule
        blocks the task, or ``allowed=False`` with a human-readable reason.

        The first blocking rule wins; subsequent rules are not evaluated.
        """
        with self._lock:
            rules_snapshot = list(self._rules)

        for idx, rule in enumerate(rules_snapshot):
            rule_type = rule.get("type", "")

            if rule_type == "constitutional_guard":
                reason = self._check_constitutional_guard(task, rule)
                if reason is not None:
                    return PolicyVerdict(allowed=False, reason=reason)

            elif rule_type == "rate_limit":
                reason = self._check_rate_limit_locked(task, rule, idx)
                if reason is not None:
                    return PolicyVerdict(allowed=False, reason=reason)

            elif rule_type == "approval_required":
                # Approval enforcement is the Sovereign's responsibility;
                # the engine just signals that approval *may* be required.
                # We intentionally return allowed=True here.
                reason = self._check_approval_required(task, rule)
                # reason is non-None when rule matches — still allowed
                _ = reason  # consumed only for the public helper contract

        return PolicyVerdict(allowed=True, reason="ok")

    # ------------------------------------------------------------------
    # Per-type checkers (public for direct unit-testing convenience)
    # ------------------------------------------------------------------

    def _check_rate_limit(self, task: Any) -> str | None:
        """Check the *first* rate_limit rule that matches *task*.

        Public wrapper used by tests; internally delegates to the
        index-aware locked version.
        """
        with self._lock:
            rules_snapshot = list(self._rules)

        for idx, rule in enumerate(rules_snapshot):
            if rule.get("type") == "rate_limit":
                reason = self._check_rate_limit_locked(task, rule, idx)
                if reason is not None:
                    return reason
        return None

    def _check_approval_required(self, task: Any, rule: dict | None = None) -> str | None:
        """Return a description string if an approval_required rule matches *task*, else None."""
        if rule is None:
            # search first matching rule
            with self._lock:
                rules_snapshot = list(self._rules)
            for r in rules_snapshot:
                if r.get("type") == "approval_required" and _match(task, r.get("match", {})):
                    approvers = r.get("approvers", [])
                    return f"approval required from: {', '.join(approvers) or 'sovereign'}"
            return None

        if _match(task, rule.get("match", {})):
            approvers = rule.get("approvers", [])
            return f"approval required from: {', '.join(approvers) or 'sovereign'}"
        return None

    def _check_constitutional_guard(self, task: Any, rule: dict | None = None) -> str | None:
        """Return deny_reason if a constitutional_guard rule matches *task*, else None."""
        if rule is None:
            with self._lock:
                rules_snapshot = list(self._rules)
            for r in rules_snapshot:
                if r.get("type") == "constitutional_guard" and _match(task, r.get("match", {})):
                    return r.get("deny_reason", "blocked by constitutional guard")
            return None

        if _match(task, rule.get("match", {})):
            return rule.get("deny_reason", "blocked by constitutional guard")
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_rate_limit_locked(
        self,
        task: Any,
        rule: dict[str, Any],
        idx: int,
    ) -> str | None:
        """Evaluate one rate_limit rule.  Must be called with *self._lock released*
        (it acquires its own lock internally for counter mutation).
        """
        if not _match(task, rule.get("match", {})):
            return None

        max_per_minute: int = int(rule.get("max_per_minute", 60))
        window_seconds: float = float(rule.get("window_seconds", 60))
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            timestamps = self._rate_counters.get(idx, [])
            # Prune old entries
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= max_per_minute:
                # Don't record this attempt — it's blocked
                self._rate_counters[idx] = timestamps
                return (
                    f"rate limit exceeded: max {max_per_minute} per "
                    f"{window_seconds}s window"
                )
            # Record this dispatch
            timestamps.append(now)
            self._rate_counters[idx] = timestamps

        return None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _match(task: Any, match: dict[str, Any]) -> bool:
    """Return True when all key/value pairs in *match* are satisfied by
    ``task.metadata``.

    * An empty *match* dict matches every task.
    * String metadata values use substring containment.
    * Non-string metadata values use equality.
    """
    if not match:
        return True  # empty match → applies to all tasks

    metadata: dict[str, Any] = getattr(task, "metadata", {}) or {}

    for key, pattern in match.items():
        actual = metadata.get(key)
        if actual is None:
            return False
        if isinstance(pattern, str) and isinstance(actual, str):
            if pattern not in actual:
                return False
        else:
            if actual != pattern:
                return False
    return True
