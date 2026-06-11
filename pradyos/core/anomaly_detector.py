"""Phase 69 — Sovereign Signal Anomaly Detector.

Detects statistical outliers in a named :class:`SignalAggregator` signal by
scoring the most recent value against the mean and standard deviation of the
windowed history. Pure stdlib — no numpy/scipy.

Readings inside the window are downsampled into 1-second buckets (the mean of
all readings sharing the same ``floor(recorded_at)``), giving a stable,
sampling-rate-independent baseline. The latest bucket's value is then expressed
as a z-score and mapped to a qualitative severity label.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from pradyos.core.signal_aggregator import SignalAggregator


def _severity(z: float) -> str:
    """Map a z-score to a severity label using its absolute magnitude."""
    az = abs(z)
    if az >= 3.0:
        return "critical"
    if az >= 2.0:
        return "warning"
    return "normal"


@dataclass
class AnomalyResult:
    """Outcome of a single anomaly evaluation over a signal's recent window."""

    signal: str
    sample_size: int  # overlapping 1-second bucket count used
    window: float  # seconds of history used
    mean: float  # mean of bucket values, rounded to 6 dp
    stddev: float  # population stddev of bucket values, rounded to 6 dp
    latest_value: float  # value of the most recent bucket, rounded to 6 dp
    z_score: float  # (latest - mean) / stddev, rounded to 6 dp; 0.0 if stddev == 0
    severity: str  # qualitative label (see _severity thresholds)
    computed_at: float  # time.time()

    def to_dict(self) -> dict:
        """Return all fields as a plain JSON-serialisable dict."""
        return {
            "signal": self.signal,
            "sample_size": self.sample_size,
            "window": self.window,
            "mean": self.mean,
            "stddev": self.stddev,
            "latest_value": self.latest_value,
            "z_score": self.z_score,
            "severity": self.severity,
            "computed_at": self.computed_at,
        }


class AnomalyDetector:
    """Detects statistical outliers in a named signal via z-score scoring."""

    def __init__(self, aggregator: SignalAggregator) -> None:
        """Hold a reference to the shared SignalAggregator. Thread-safe; LRU cache max 128."""
        self._aggregator = aggregator
        self._lock = threading.Lock()
        self._cache: dict[tuple, AnomalyResult] = {}
        self._cache_order: list[tuple] = []  # oldest-first insertion order

    def detect(self, signal: str, window: float = 3600.0) -> AnomalyResult:
        """Score the most recent value of ``signal`` against its windowed mean/stddev."""
        now = time.time()
        cutoff = now - window

        points = [p for p in self._aggregator.get(signal, limit=100_000) if p.recorded_at >= cutoff]

        # Bucket into 1-second bins: value = mean of readings sharing floor(ts).
        sums: dict[int, float] = {}
        counts: dict[int, int] = {}
        for p in points:
            key = math.floor(p.recorded_at)
            sums[key] = sums.get(key, 0.0) + p.value
            counts[key] = counts.get(key, 0) + 1

        ts_sorted = sorted(sums)
        vals = [sums[t] / counts[t] for t in ts_sorted]
        n = len(vals)

        if n == 0:
            return AnomalyResult(
                signal=signal,
                sample_size=0,
                window=window,
                mean=0.0,
                stddev=0.0,
                latest_value=0.0,
                z_score=0.0,
                severity="normal",
                computed_at=time.time(),
            )

        latest_value = vals[-1]
        mean = sum(vals) / n

        if n < 2:
            # A single bucket has no spread; it cannot be an outlier of itself.
            return AnomalyResult(
                signal=signal,
                sample_size=n,
                window=window,
                mean=round(mean, 6),
                stddev=0.0,
                latest_value=round(latest_value, 6),
                z_score=0.0,
                severity="normal",
                computed_at=time.time(),
            )

        variance = sum((v - mean) ** 2 for v in vals) / n
        stddev = math.sqrt(variance)
        z = 0.0 if stddev == 0.0 else (latest_value - mean) / stddev

        return AnomalyResult(
            signal=signal,
            sample_size=n,
            window=window,
            mean=round(mean, 6),
            stddev=round(stddev, 6),
            latest_value=round(latest_value, 6),
            z_score=round(z, 6),
            severity=_severity(z),
            computed_at=time.time(),
        )

    def get_cached(self, signal: str, window: float) -> AnomalyResult | None:
        """Return the cached result for the exact (signal, window) key, or None."""
        key = (signal, window)
        with self._lock:
            return self._cache.get(key)

    def cache_result(self, result: AnomalyResult) -> None:
        """Store ``result`` in the LRU cache, evicting the oldest beyond 128 entries."""
        key = (result.signal, result.window)
        with self._lock:
            if key in self._cache:
                self._cache_order.remove(key)
            self._cache[key] = result
            self._cache_order.append(key)
            while len(self._cache) > 128:
                oldest = self._cache_order.pop(0)
                self._cache.pop(oldest, None)
