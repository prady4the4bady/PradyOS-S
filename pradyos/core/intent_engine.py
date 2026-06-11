"""Phase 19 — Sovereign Intent Engine.

Rule-based planner that evaluates system context against a configurable rule
set and produces ranked IntentSuggestion objects.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# IntentSuggestion
# ---------------------------------------------------------------------------


@dataclass
class IntentSuggestion:
    """A single actionable suggestion produced by the IntentEngine."""

    action: str
    target: str
    reason: str
    confidence: float
    suggestion_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "action": self.action,
            "target": self.target,
            "reason": self.reason,
            "confidence": self.confidence,
            "ts": self.ts,
        }


# ---------------------------------------------------------------------------
# IntentEngine
# ---------------------------------------------------------------------------

_SUPPORTED_CONDITIONS = frozenset(
    {
        "graph_nodes_gt",
        "error_span_rate_gt",
        "active_campaigns_lt",
        "ledger_events_gt",
    }
)


class IntentEngine:
    """Evaluates a rule set against runtime context and emits suggestions."""

    def __init__(self, rules: list[dict] | None = None) -> None:
        self._lock = threading.Lock()
        self._rules: list[dict] = list(rules) if rules else []

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def load_rules(self, rules: list[dict]) -> None:
        """Replace the current rule set (thread-safe)."""
        with self._lock:
            self._rules = list(rules)

    def get_rules(self) -> list[dict]:
        """Return an independent copy of the current rule set."""
        with self._lock:
            return list(self._rules)

    # ------------------------------------------------------------------
    # Suggestion engine
    # ------------------------------------------------------------------

    def suggest(
        self,
        graph_stats: dict | None = None,
        active_campaigns: list[dict] | None = None,
        recent_spans: list[dict] | None = None,
        recent_entries: list[dict] | None = None,
    ) -> list[IntentSuggestion]:
        """Evaluate all rules against the provided context.

        Returns a list of IntentSuggestion (one per matched rule).  Rules
        with an unrecognised condition are silently skipped.
        """
        with self._lock:
            rules_snapshot = list(self._rules)

        suggestions: list[IntentSuggestion] = []

        for rule in rules_snapshot:
            condition = rule.get("condition", "")
            threshold = float(rule.get("threshold", 0))

            if condition not in _SUPPORTED_CONDITIONS:
                # silently skip unknown conditions
                continue

            fired = _evaluate_condition(
                condition=condition,
                threshold=threshold,
                graph_stats=graph_stats,
                active_campaigns=active_campaigns,
                recent_spans=recent_spans,
                recent_entries=recent_entries,
            )

            if fired:
                suggestions.append(
                    IntentSuggestion(
                        action=rule.get("action", ""),
                        target=rule.get("target", ""),
                        reason=rule.get("reason", ""),
                        confidence=float(rule.get("confidence", 0.0)),
                    )
                )

        return suggestions


# ---------------------------------------------------------------------------
# Condition evaluation helpers
# ---------------------------------------------------------------------------


def _evaluate_condition(
    condition: str,
    threshold: float,
    *,
    graph_stats: dict | None,
    active_campaigns: list[dict] | None,
    recent_spans: list[dict] | None,
    recent_entries: list[dict] | None,
) -> bool:
    if condition == "graph_nodes_gt":
        if graph_stats is None:
            return False
        node_count = graph_stats.get("nodes", 0)
        return int(node_count) > threshold

    if condition == "error_span_rate_gt":
        if not recent_spans:
            return False
        total = len(recent_spans)
        errors = sum(1 for s in recent_spans if s.get("status") == "error")
        return (errors / total) > threshold

    if condition == "active_campaigns_lt":
        if active_campaigns is None:
            return False
        return len(active_campaigns) < threshold

    if condition == "ledger_events_gt":
        if not recent_entries:
            return False
        return len(recent_entries) > threshold

    return False  # unreachable for supported conditions, but safe fallback
