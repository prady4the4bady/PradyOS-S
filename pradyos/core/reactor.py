from __future__ import annotations

import collections
import threading
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class ReactorRule:
    rule_id: str
    decision_type: str
    action: str
    context_filter: dict
    created_at: float

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "decision_type": self.decision_type,
            "action": self.action,
            "context_filter": dict(self.context_filter),
            "created_at": self.created_at,
        }


@dataclass
class ReactionEvent:
    reaction_id: str
    rule_id: str
    decision_type: str
    action: str
    fired_at: float
    context: dict

    def to_dict(self) -> dict:
        return {
            "reaction_id": self.reaction_id,
            "rule_id": self.rule_id,
            "decision_type": self.decision_type,
            "action": self.action,
            "fired_at": self.fired_at,
            "context": dict(self.context),
        }


class ReactorEngine:
    def __init__(self, max_log: int = 1000) -> None:
        self._rules: dict[str, ReactorRule] = {}
        self._log: collections.deque[ReactionEvent] = collections.deque(maxlen=max_log)
        self._lock = threading.Lock()

    def add_rule(
        self,
        decision_type: str,
        action: str,
        context_filter: dict | None = None,
    ) -> ReactorRule:
        rule = ReactorRule(
            rule_id=uuid.uuid4().hex,
            decision_type=decision_type,
            action=action,
            context_filter=dict(context_filter) if context_filter else {},
            created_at=time.time(),
        )
        with self._lock:
            self._rules[rule.rule_id] = rule
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                return True
        return False

    def list_rules(self) -> list[dict]:
        with self._lock:
            rules = sorted(self._rules.values(), key=lambda r: r.created_at)
        return [r.to_dict() for r in rules]

    def react(self, entry) -> list[ReactionEvent]:
        fired: list[ReactionEvent] = []
        with self._lock:
            rules_snapshot = list(self._rules.values())

        for rule in rules_snapshot:
            if rule.decision_type != entry.decision_type:
                continue
            if rule.context_filter and not all(
                str(v) in entry.rationale for v in rule.context_filter.values()
            ):
                # context_filter values must each appear as substring in rationale
                continue
            event = ReactionEvent(
                reaction_id=uuid.uuid4().hex,
                rule_id=rule.rule_id,
                decision_type=entry.decision_type,
                action=rule.action,
                fired_at=time.time(),
                context={"rationale": entry.rationale, "outcome": entry.outcome},
            )
            with self._lock:
                self._log.append(event)
            fired.append(event)

        return fired

    def get_log(self, limit: int = 100) -> list[ReactionEvent]:
        with self._lock:
            events = list(self._log)
        return events[-limit:]

    def count(self) -> dict:
        with self._lock:
            return {"rules": len(self._rules), "reactions": len(self._log)}
