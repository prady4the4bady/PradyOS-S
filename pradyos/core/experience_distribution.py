"""Experience Distribution Tracker — the OS's sense of "what is normal" (cognitive layer).

A per-metric streaming distribution tracker and anomaly scorer. For any named
metric (e.g. ``response_latency_ms``) it maintains the running quantiles of the
OS's own operational experience and scores how *abnormal* a new value is — the
machine's proprioception.

It **composes** two shipped sketches (never reimplements them):

  * **TDigest** — smooth, accurate streaming quantiles for unbounded *continuous*
    metrics. This is the workhorse: it drives ``percentile`` and ``anomaly_score``.
  * **DDSketch** — relative-error quantiles (γ-bucketed). It is a *positive-value*
    structure, so it is fed only ``value > 0`` (the T-Digest carries the full range
    incl. 0/negatives); maintained as a relative-accuracy cross-check on the
    positive subset, surfaced in ``distribution_summary``.

**Q-Digest is intentionally omitted** per metric: it is a *bounded-integer-universe*
structure (``add(value: int)`` over a declared range) — the right tool for integer
metrics with a known max, the wrong tool for arbitrary unbounded floats. Forcing
float metrics into it would require lossy quantization. Honest composition uses the
two structures that actually fit the data; the omission is documented rather than
papered over.

**Anomaly score** is the robust *modified-z analog*::

  anomaly = |value − p50| / (IQR + ε),   IQR = p75 − p25

robust to outliers (unlike mean/stdev) and distribution-agnostic. ~0 for a typical
value, large for a tail outlier.

Design: deterministic, thread-safe (one RLock), metrics auto-created on first
observe.
"""

from __future__ import annotations

import threading
from typing import Any

from pradyos.core.ddsketch import DDSketch
from pradyos.core.tdigest import TDigest

__all__ = ["ExperienceDistribution", "ExperienceDistributionError"]

_EPS = 1e-9


class ExperienceDistributionError(Exception):
    """Raised on invalid ExperienceDistribution operations."""


class ExperienceDistribution:
    """Per-metric streaming percentiles + IQR-based anomaly scoring."""

    def __init__(
        self,
        metrics: list[str] | None = None,
        alpha: float = 0.01,
        compression: float = 100.0,
        seed: int = 0,
    ) -> None:
        if not (isinstance(alpha, (int, float)) and 0.0 < alpha < 1.0):
            raise ExperienceDistributionError("alpha must be in (0, 1)")
        if not (isinstance(compression, (int, float)) and compression > 0):
            raise ExperienceDistributionError("compression must be positive")
        self._alpha = float(alpha)
        self._compression = float(compression)
        self._seed = int(seed)
        self._metrics: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        for m in metrics or []:
            self._ensure(str(m))

    def _ensure(self, metric: str) -> dict[str, Any]:
        slot = self._metrics.get(metric)
        if slot is None:
            slot = {
                "td": TDigest(compression=self._compression),
                "dd": DDSketch(alpha=self._alpha, seed=self._seed),
                "count": 0,
            }
            self._metrics[metric] = slot
        return slot

    def _require(self, metric: str) -> dict[str, Any]:
        slot = self._metrics.get(metric)
        if slot is None or slot["count"] == 0:
            raise ExperienceDistributionError(f"no observations for metric {metric!r}")
        return slot

    # ── write ──────────────────────────────────────────────────────────────────

    def observe(self, metric: str, value: float) -> None:
        """Record an observation; the metric is auto-created on first sight."""
        if not (isinstance(metric, str) and metric.strip()):
            raise ExperienceDistributionError("metric must be a non-empty string")
        try:
            v = float(value)
        except (TypeError, ValueError) as exc:
            raise ExperienceDistributionError("value must be a number") from exc
        with self._lock:
            slot = self._ensure(metric)
            slot["td"].add(v)
            # DDSketch is a positive-value (log-bucketed) structure; the T-Digest
            # carries the full range (incl. 0 / negatives), the DDSketch cross-check
            # covers the positive subset only.
            if v > 0:
                slot["dd"].update(v)
            slot["count"] += 1

    # ── read ───────────────────────────────────────────────────────────────────

    def percentile(self, metric: str, q: float) -> float:
        """q-th percentile (q in (0,1)) from the T-Digest."""
        if not (isinstance(q, (int, float)) and 0.0 < q < 1.0):
            raise ExperienceDistributionError("q must be in (0, 1)")
        with self._lock:
            return float(self._require(metric)["td"].quantile(q))

    def anomaly_score(self, metric: str, value: float) -> float:
        """Robust modified-z analog: |value − p50| / (IQR + ε)."""
        try:
            v = float(value)
        except (TypeError, ValueError) as exc:
            raise ExperienceDistributionError("value must be a number") from exc
        with self._lock:
            td = self._require(metric)["td"]
            p50 = float(td.quantile(0.5))
            iqr = float(td.quantile(0.75)) - float(td.quantile(0.25))
        return abs(v - p50) / (iqr + _EPS)

    def distribution_summary(self, metric: str) -> dict[str, Any]:
        """{p25, p50, p75, p90, p99, min, max, count} for the metric."""
        with self._lock:
            slot = self._require(metric)
            td = slot["td"]
            return {
                "count": slot["count"],
                "min": float(td.min),
                "p25": float(td.quantile(0.25)),
                "p50": float(td.quantile(0.5)),
                "p75": float(td.quantile(0.75)),
                "p90": float(td.quantile(0.9)),
                "p99": float(td.quantile(0.99)),
                "max": float(td.max),
                "ddsketch_p50": (lambda x: float(x) if x is not None else None)(slot["dd"].quantile(0.5)),
            }

    def list_metrics(self) -> list[str]:
        with self._lock:
            return sorted(self._metrics)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "num_metrics": len(self._metrics),
                "total_observations": sum(s["count"] for s in self._metrics.values()),
                "alpha": self._alpha,
                "compression": self._compression,
                "seed": self._seed,
                "metrics": {m: s["count"] for m, s in self._metrics.items()},
            }

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()
