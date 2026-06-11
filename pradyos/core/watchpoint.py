from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass

SEVERITY_LEVELS = ["info", "warn", "critical"]
_OPERATORS = ("gt", "lt", "gte", "lte", "eq")


@dataclass
class Watchpoint:
    name: str
    metric: str
    operator: str
    threshold: float
    severity: str
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "metric": self.metric,
            "operator": self.operator,
            "threshold": self.threshold,
            "severity": self.severity,
            "enabled": self.enabled,
        }


@dataclass
class Alert:
    watchpoint_name: str
    metric: str
    operator: str
    threshold: float
    actual_value: float
    severity: str
    fired_at: float

    def to_dict(self) -> dict:
        return {
            "watchpoint_name": self.watchpoint_name,
            "metric": self.metric,
            "operator": self.operator,
            "threshold": self.threshold,
            "actual_value": self.actual_value,
            "severity": self.severity,
            "fired_at": self.fired_at,
        }


def _evaluate(operator: str, value: float, threshold: float) -> bool:
    if operator == "gt":
        return value > threshold
    if operator == "lt":
        return value < threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lte":
        return value <= threshold
    if operator == "eq":
        return value == threshold
    return False


class WatchpointSystem:
    def __init__(self, max_alerts: int = 1000) -> None:
        self.watchpoints: dict[str, Watchpoint] = {}
        self._alerts: collections.deque[Alert] = collections.deque(maxlen=max_alerts)
        self._total_alerts: int = 0
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        metric: str,
        operator: str,
        threshold: float,
        severity: str = "warn",
        enabled: bool = True,
    ) -> Watchpoint:
        if operator not in _OPERATORS:
            raise ValueError(f"Invalid operator: {operator!r}. Must be one of {_OPERATORS}")
        if severity not in SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity: {severity!r}. Must be one of {SEVERITY_LEVELS}")
        wp = Watchpoint(
            name=name,
            metric=metric,
            operator=operator,
            threshold=threshold,
            severity=severity,
            enabled=enabled,
        )
        with self._lock:
            self.watchpoints[name] = wp
        return wp

    def check(self, metric: str, value: float) -> list[Alert]:
        fired: list[Alert] = []
        with self._lock:
            candidates = [
                wp for wp in self.watchpoints.values() if wp.metric == metric and wp.enabled
            ]
        for wp in candidates:
            if _evaluate(wp.operator, value, wp.threshold):
                alert = Alert(
                    watchpoint_name=wp.name,
                    metric=wp.metric,
                    operator=wp.operator,
                    threshold=wp.threshold,
                    actual_value=value,
                    severity=wp.severity,
                    fired_at=time.time(),
                )
                with self._lock:
                    self._alerts.append(alert)
                    self._total_alerts += 1
                fired.append(alert)
        return fired

    def get_alerts(
        self,
        watchpoint_name: str | None = None,
        severity: str | None = None,
        limit: int | None = None,
    ) -> list[Alert]:
        with self._lock:
            alerts = list(self._alerts)
        if watchpoint_name is not None:
            alerts = [a for a in alerts if a.watchpoint_name == watchpoint_name]
        if severity is not None:
            alerts = [a for a in alerts if a.severity == severity]
        if limit is not None:
            alerts = alerts[:limit]
        return alerts

    def get_watchpoints(self) -> list[Watchpoint]:
        with self._lock:
            return sorted(self.watchpoints.values(), key=lambda w: w.name)

    def disable(self, name: str) -> bool:
        with self._lock:
            if name in self.watchpoints:
                self.watchpoints[name].enabled = False
                return True
        return False

    def enable(self, name: str) -> bool:
        with self._lock:
            if name in self.watchpoints:
                self.watchpoints[name].enabled = True
                return True
        return False

    def status(self) -> dict:
        with self._lock:
            total = len(self.watchpoints)
            enabled = sum(1 for w in self.watchpoints.values() if w.enabled)
            total_ever = self._total_alerts
            in_buffer = len(self._alerts)
        return {
            "total_watchpoints": total,
            "enabled": enabled,
            "total_alerts_ever": total_ever,
            "alerts_in_buffer": in_buffer,
        }
