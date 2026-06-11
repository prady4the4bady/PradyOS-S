"""Phase 24: Sovereign Health Scorecard — composite score engine."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class ComponentScore:
    name: str
    score: float  # 0.0–100.0
    weight: float  # relative weight (not normalised)
    details: dict  # arbitrary key-value context

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "details": self.details,
        }


@dataclass
class HealthReport:
    score: float  # 0.0–100.0 composite weighted average
    grade: str  # "A" ≥90, "B" ≥75, "C" ≥60, "D" ≥40, "F" <40
    components: list  # list[ComponentScore]
    timestamp: float  # time.time()

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "grade": self.grade,
            "components": [c.to_dict() for c in self.components],
            "timestamp": self.timestamp,
        }


def _compute_grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


class HealthScorecard:
    """Thread-safe composite health score registry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # name -> {"weight": float, "score": float | None, "details": dict}
        self._components: dict[str, dict] = {}

    def register(self, name: str, weight: float = 1.0) -> None:
        """Register a component with its weight. Overwrites if already present."""
        with self._lock:
            existing_score = None
            existing_details: dict = {}
            if name in self._components:
                existing_score = self._components[name].get("score")
                existing_details = self._components[name].get("details", {})
            self._components[name] = {
                "weight": weight,
                "score": existing_score,
                "details": existing_details,
            }

    def update(
        self,
        name: str,
        score: float,
        details: dict | None = None,
    ) -> None:
        """Set current score (0–100) for a named component.

        Clamps to [0, 100]. Auto-registers with weight=1.0 if unknown.
        """
        clamped = max(0.0, min(100.0, float(score)))
        if details is None:
            details = {}
        with self._lock:
            if name not in self._components:
                self._components[name] = {"weight": 1.0, "score": None, "details": {}}
            self._components[name]["score"] = clamped
            self._components[name]["details"] = details

    def get_report(self) -> HealthReport:
        """Compute weighted-average composite score across updated components."""
        with self._lock:
            updated = {n: v for n, v in self._components.items() if v["score"] is not None}

        if not updated:
            return HealthReport(
                score=100.0,
                grade="A",
                components=[],
                timestamp=time.time(),
            )

        total_weight = sum(v["weight"] for v in updated.values())
        if total_weight == 0:
            composite = 100.0
        else:
            composite = sum(v["score"] * v["weight"] for v in updated.values()) / total_weight

        composite = max(0.0, min(100.0, composite))
        grade = _compute_grade(composite)

        components = [
            ComponentScore(
                name=n,
                score=v["score"],
                weight=v["weight"],
                details=v["details"],
            )
            for n, v in updated.items()
        ]

        return HealthReport(
            score=composite,
            grade=grade,
            components=components,
            timestamp=time.time(),
        )

    def reset(self, name: str | None = None) -> None:
        """Remove a single component (if name given) or clear all."""
        with self._lock:
            if name is None:
                self._components.clear()
            elif name in self._components:
                del self._components[name]
