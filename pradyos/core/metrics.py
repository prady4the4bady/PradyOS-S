"""Metrics Collector — Phase 6 Observability Layer.

Provides Counter, Gauge, and Histogram metric primitives and a
MetricsRegistry singleton that feeds the /api/metrics endpoint.

Thread-safe. Zero external dependencies.
Windows-safe: no fork(), no signals, all stdlib.
"""

from __future__ import annotations

import math
import threading
from typing import Any

# ---------------------------------------------------------------------------
# Metric primitives
# ---------------------------------------------------------------------------


class Counter:
    """Monotonically increasing counter.

    inc(amount=1) — increment by *amount* (must be >= 0).
    value          — current total.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name        = name
        self.description = description
        self._value      = 0.0
        self._lock       = threading.Lock()

    def inc(self, amount: float = 1.0) -> None:
        if amount < 0:
            raise ValueError(f"Counter.inc() amount must be >= 0, got {amount}")
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        with self._lock:
            return self._value

    def snapshot(self) -> dict[str, Any]:
        return {"type": "counter", "name": self.name, "value": self.value,
                "description": self.description}


class Gauge:
    """Freely settable numeric value.

    set(v)  — set to exactly *v*.
    inc(d)  — increment by *d* (positive or negative).
    value   — current value.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name        = name
        self.description = description
        self._value      = 0.0
        self._lock       = threading.Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = float(value)

    def inc(self, delta: float = 1.0) -> None:
        with self._lock:
            self._value += delta

    @property
    def value(self) -> float:
        with self._lock:
            return self._value

    def snapshot(self) -> dict[str, Any]:
        return {"type": "gauge", "name": self.name, "value": self.value,
                "description": self.description}


class Histogram:
    """Tracks a distribution of observed values.

    observe(v)   — record a single observation.
    count        — number of observations.
    sum_         — cumulative sum.
    mean         — arithmetic mean (NaN if no observations).
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: list[float] | None = None,
    ) -> None:
        self.name        = name
        self.description = description
        # Default exponential buckets (ms-scale friendly)
        self._buckets    = sorted(buckets or [0.005, 0.01, 0.025, 0.05, 0.1,
                                               0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
        self._counts     = [0] * len(self._buckets)  # le-bucket counts
        self._inf_count  = 0   # observations > largest bucket
        self._total      = 0
        self._sum        = 0.0
        self._lock       = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._total += 1
            self._sum   += value
            placed = False
            for i, upper in enumerate(self._buckets):
                if value <= upper:
                    self._counts[i] += 1
                    placed = True
                    break
            if not placed:
                self._inf_count += 1

    @property
    def count(self) -> int:
        with self._lock:
            return self._total

    @property
    def sum_(self) -> float:
        with self._lock:
            return self._sum

    @property
    def mean(self) -> float:
        with self._lock:
            if self._total == 0:
                return float("nan")
            return self._sum / self._total

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            bucket_data = [
                {"le": upper, "count": cnt}
                for upper, cnt in zip(self._buckets, self._counts)
            ]
            bucket_data.append({"le": "+Inf", "count": self._inf_count})
            return {
                "type":        "histogram",
                "name":        self.name,
                "description": self.description,
                "count":       self._total,
                "sum":         self._sum,
                "mean":        (self._sum / self._total) if self._total else None,
                "buckets":     bucket_data,
            }


# ---------------------------------------------------------------------------
# MetricsRegistry — singleton
# ---------------------------------------------------------------------------


class MetricsRegistry:
    """Thread-safe registry of named metrics.

    register(metric)  — add a Counter/Gauge/Histogram.
    get(name)         — retrieve by name (or None).
    snapshot()        — dict of name → metric snapshot dict.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, Any] = {}
        self._lock = threading.Lock()

    def register(self, metric: Counter | Gauge | Histogram) -> None:
        with self._lock:
            self._metrics[metric.name] = metric

    def get(self, name: str) -> Counter | Gauge | Histogram | None:
        with self._lock:
            return self._metrics.get(name)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {name: m.snapshot() for name, m in self._metrics.items()}

    def clear(self) -> None:
        """Remove all metrics — used in tests."""
        with self._lock:
            self._metrics.clear()


# Process-wide singleton
_registry_instance: MetricsRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> MetricsRegistry:
    """Return the process-wide MetricsRegistry singleton."""
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = MetricsRegistry()
    return _registry_instance


def reset_registry_for_tests() -> MetricsRegistry:
    """Replace singleton — tests only."""
    global _registry_instance
    with _registry_lock:
        _registry_instance = MetricsRegistry()
    return _registry_instance
