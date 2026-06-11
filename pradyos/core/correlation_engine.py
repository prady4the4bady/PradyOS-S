from __future__ import annotations

import math
import time
from dataclasses import dataclass

from pradyos.core.signal_aggregator import SignalAggregator


def _label(r: float) -> str:
    if math.isnan(r):
        return "weak"
    if r >= 0.7:
        return "strong-positive"
    if r >= 0.4:
        return "moderate-positive"
    if r > -0.4:
        return "weak"
    if r > -0.7:
        return "moderate-negative"
    return "strong-negative"


@dataclass
class CorrelationResult:
    signal_a: str
    signal_b: str
    coefficient: float
    sample_size: int
    label: str
    window_secs: float
    computed_at: float

    def to_dict(self) -> dict:
        coeff = self.coefficient
        return {
            "signal_a": self.signal_a,
            "signal_b": self.signal_b,
            "coefficient": None if math.isnan(coeff) else coeff,
            "sample_size": self.sample_size,
            "label": self.label,
            "window_secs": self.window_secs,
            "computed_at": self.computed_at,
        }


class CorrelationEngine:
    def __init__(self, signal_aggregator: SignalAggregator) -> None:
        self._agg = signal_aggregator

    def correlate(
        self,
        signal_a: str,
        signal_b: str,
        window_secs: float = 3600.0,
    ) -> CorrelationResult:
        now = time.time()
        cutoff = now - window_secs

        pts_a = [p for p in self._agg.get(signal_a, limit=100_000) if p.recorded_at >= cutoff]
        pts_b = [p for p in self._agg.get(signal_b, limit=100_000) if p.recorded_at >= cutoff]

        nan = float("nan")
        computed_at = time.time()

        if not pts_a or not pts_b:
            return CorrelationResult(
                signal_a=signal_a,
                signal_b=signal_b,
                coefficient=nan,
                sample_size=0,
                label="weak",
                window_secs=window_secs,
                computed_at=computed_at,
            )

        # nearest-neighbour pairing — iterate shorter, match into longer
        if len(pts_a) <= len(pts_b):
            primary, secondary = pts_a, pts_b
        else:
            primary, secondary = pts_b, pts_a

        used: set[int] = set()
        pairs_p: list[float] = []
        pairs_s: list[float] = []

        for pp in primary:
            best_idx = -1
            best_dist = float("inf")
            for idx, sp in enumerate(secondary):
                if idx in used:
                    continue
                dist = abs(pp.recorded_at - sp.recorded_at)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx
            if best_idx >= 0:
                used.add(best_idx)
                pairs_p.append(pp.value)
                pairs_s.append(secondary[best_idx].value)

        # restore original a/b order
        if len(pts_a) <= len(pts_b):
            vals_a, vals_b = pairs_p, pairs_s
        else:
            vals_a, vals_b = pairs_s, pairs_p

        n = len(vals_a)
        if n < 2:
            return CorrelationResult(
                signal_a=signal_a,
                signal_b=signal_b,
                coefficient=nan,
                sample_size=n,
                label="weak",
                window_secs=window_secs,
                computed_at=computed_at,
            )

        mean_a = sum(vals_a) / n
        mean_b = sum(vals_b) / n
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(vals_a, vals_b, strict=False)) / n
        std_a = math.sqrt(sum((a - mean_a) ** 2 for a in vals_a) / n)
        std_b = math.sqrt(sum((b - mean_b) ** 2 for b in vals_b) / n)

        if std_a == 0.0 or std_b == 0.0:
            r = nan
        else:
            r = cov / (std_a * std_b)

        return CorrelationResult(
            signal_a=signal_a,
            signal_b=signal_b,
            coefficient=r,
            sample_size=n,
            label=_label(r),
            window_secs=window_secs,
            computed_at=computed_at,
        )
