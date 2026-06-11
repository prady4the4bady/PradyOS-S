from __future__ import annotations

import threading
import time
from dataclasses import dataclass

_REQUIRED_RULE_KEYS = ("trigger", "action", "risk_level", "rationale", "preconditions")


@dataclass
class ReasoningStep:
    action: str
    risk_level: str
    rationale: str
    preconditions: dict

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "risk_level": self.risk_level,
            "rationale": self.rationale,
            "preconditions": dict(self.preconditions),
        }


@dataclass
class ReasoningPlan:
    goal: str
    steps: list[ReasoningStep]
    confidence: float
    state_used: dict
    created_at: float

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "confidence": self.confidence,
            "state_used": dict(self.state_used),
            "created_at": self.created_at,
        }


def _preconditions_satisfied(preconditions: dict, state: dict) -> bool:
    """All k/v pairs in preconditions match state."""
    for k, v in preconditions.items():
        if state.get(k) != v:
            return False
    return True


class ReasoningEngine:
    def __init__(self, rules: list[dict] | None = None) -> None:
        self._rules: list[dict] = []
        self._lock = threading.Lock()
        if rules:
            for r in rules:
                self.add_rule(r)

    def add_rule(self, rule: dict) -> None:
        for key in _REQUIRED_RULE_KEYS:
            if key not in rule:
                raise ValueError(f"Rule missing required key: {key!r}")
        with self._lock:
            self._rules.append(
                {
                    "trigger": rule["trigger"],
                    "action": rule["action"],
                    "risk_level": rule["risk_level"],
                    "rationale": rule["rationale"],
                    "preconditions": dict(rule["preconditions"]),
                }
            )

    def rule_count(self) -> int:
        with self._lock:
            return len(self._rules)

    def plan(self, goal: str, state: dict) -> ReasoningPlan:
        with self._lock:
            rules_snapshot = [dict(r) for r in self._rules]

        goal_lower = goal.lower()
        matched: list[ReasoningStep] = []
        for r in rules_snapshot:
            if str(r["trigger"]).lower() not in goal_lower:
                continue
            matched.append(
                ReasoningStep(
                    action=r["action"],
                    risk_level=r["risk_level"],
                    rationale=r["rationale"],
                    preconditions=dict(r["preconditions"]),
                )
            )

        # Order: satisfied preconditions first, then unsatisfied;
        # preserve original order within each group.
        satisfied: list[ReasoningStep] = []
        unsatisfied: list[ReasoningStep] = []
        for step in matched:
            if _preconditions_satisfied(step.preconditions, state):
                satisfied.append(step)
            else:
                unsatisfied.append(step)
        ordered = satisfied + unsatisfied

        # Confidence: ratio of satisfied precondition pairs over total.
        total_pairs = sum(len(step.preconditions) for step in ordered)
        if not ordered or total_pairs == 0:
            confidence = 1.0
        else:
            satisfied_pairs = 0
            for step in ordered:
                for k, v in step.preconditions.items():
                    if state.get(k) == v:
                        satisfied_pairs += 1
            confidence = round(satisfied_pairs / total_pairs, 4)

        return ReasoningPlan(
            goal=goal,
            steps=ordered,
            confidence=confidence,
            state_used=dict(state),
            created_at=time.time(),
        )

    def status(self) -> dict:
        return {
            "rule_count": self.rule_count(),
            "auto_approve_levels": ["safe", "low"],
        }
