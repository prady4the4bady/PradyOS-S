from __future__ import annotations

import collections
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pradyos.core.health_scorecard import HealthScorecard


@dataclass
class HealingComponent:
    name: str
    threshold: float
    action: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "threshold": self.threshold,
            "action": self.action,
        }


@dataclass
class HealingEvent:
    event_id: str
    component: str
    score_before: float
    score_after: float
    action_taken: str
    healed_at: float

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "component": self.component,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "action_taken": self.action_taken,
            "healed_at": self.healed_at,
        }


def _scores_by_name(report) -> dict[str, float]:
    """Convert HealthReport.components (list[ComponentScore]) to {name: score}."""
    out: dict[str, float] = {}
    for c in report.components:
        # ComponentScore dataclass has .name/.score; dict fallback supported
        if hasattr(c, "name") and hasattr(c, "score"):
            out[c.name] = c.score
        elif isinstance(c, dict):
            out[c["name"]] = c["score"]
    return out


class HealingMonitor:
    def __init__(
        self,
        health_scorecard: HealthScorecard | None = None,
        max_log: int = 500,
    ) -> None:
        self._scorecard = health_scorecard
        self._components: dict[str, HealingComponent] = {}
        self._repair_fns: dict[str, Callable[[], Any]] = {}
        self._log: collections.deque[HealingEvent] = collections.deque(maxlen=max_log)
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        threshold: float,
        action: str,
        repair_fn: Callable[[], Any],
    ) -> HealingComponent:
        comp = HealingComponent(name=name, threshold=threshold, action=action)
        with self._lock:
            self._components[name] = comp
            self._repair_fns[name] = repair_fn
        return comp

    def unregister(self, name: str) -> bool:
        with self._lock:
            if name not in self._components:
                return False
            del self._components[name]
            self._repair_fns.pop(name, None)
            return True

    def list_components(self) -> list[dict]:
        with self._lock:
            comps = sorted(self._components.values(), key=lambda c: c.name)
        return [c.to_dict() for c in comps]

    def check_and_heal(self) -> list[HealingEvent]:
        if self._scorecard is None:
            return []

        report = self._scorecard.get_report()
        scores = _scores_by_name(report)

        with self._lock:
            registered = list(self._components.items())
            repair_fns = dict(self._repair_fns)

        fired: list[HealingEvent] = []
        for name, comp in registered:
            score_before = scores.get(name)
            if score_before is None:
                continue
            if score_before >= comp.threshold:
                continue

            fn = repair_fns.get(name)
            if fn is not None:
                try:
                    fn()
                except Exception:
                    pass

            # Re-read score after repair
            after_report = self._scorecard.get_report()
            after_scores = _scores_by_name(after_report)
            score_after = after_scores.get(name, score_before)

            event = HealingEvent(
                event_id=uuid.uuid4().hex,
                component=name,
                score_before=score_before,
                score_after=score_after,
                action_taken=comp.action,
                healed_at=time.time(),
            )
            with self._lock:
                self._log.append(event)
            fired.append(event)

        return fired

    def get_log(self, limit: int = 100) -> list[HealingEvent]:
        with self._lock:
            events = list(self._log)
        return events[-limit:]

    def count(self) -> dict:
        with self._lock:
            return {
                "components": len(self._components),
                "events": len(self._log),
            }
