"""Phase 125 — Sovereign Frugal Streaming quantile / Frugal-2U (Ma, Muthukrishnan & Sandler, 2014).

*Frugal Streaming for Estimating Quantiles in One Pass* — a quantile estimator that runs in
**O(1) memory** (essentially a single value), where the platform's other quantile sketches
(GK/P91, KLL/P92, t-Digest/P79, DDSketch/P96, Q-Digest/P105, Moment/P106) all keep many
summaries. It is the extreme-low-memory point of the quantile design space.

For a target quantile ``q`` it holds an estimate ``m̃`` and an adaptive integer ``step``.
On each stream item ``x`` it flips a biased coin and nudges the estimate toward ``x``:

    if x > m̃ and rand() > 1 − q:   step grows if we keep going up (else shrinks); m̃ += step; clamp to x
    if x < m̃ and rand() > q:       step grows if we keep going down (else shrinks); m̃ −= step; clamp to x

The ``step`` accelerates on consecutive same-direction moves and resets toward 1 on a
reversal — a *stochastic-approximation* chase that converges to the true ``q``-quantile of a
stationary stream and tracks a drifting one. Because it stores no buckets or centroids the
estimate is noisier than a summary sketch, but the memory is constant regardless of stream
size.

The ``Frugal-2U`` variant (used here, with unit step function) is the general-quantile
version of the original median tracker. The coin is a seeded ``random.Random`` so a fixed
seed and stream reproduce the run. Pure stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import random
import threading
from typing import Any


class FrugalError(Exception):
    """Raised for an invalid Frugal operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class FrugalQuantile:
    """O(1)-memory streaming quantile estimator (Frugal-2U)."""

    def __init__(self, quantile: float = 0.5, seed: int = 0) -> None:
        self._validate(quantile, seed)
        self._q = float(quantile)
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    @staticmethod
    def _validate(quantile: Any, seed: Any) -> None:
        if not (_is_number(quantile) and 0.0 < quantile < 1.0):
            raise FrugalError(quantile)
        if not _is_int(seed):
            raise FrugalError(seed)

    def _init_state(self) -> None:
        self._m = 0.0  # estimate
        self._step = 1.0  # adaptive step
        self._sign = 1  # last move direction (+1 up, -1 down)
        self._count = 0
        self._rng = random.Random(self._seed)

    # ── update ──────────────────────────────────────────────────────────────────────
    def add(self, value: Any) -> None:
        """Fold one stream value into the estimate (Frugal-2U update)."""
        if not _is_number(value):
            raise FrugalError(value)
        x = float(value)
        with self._lock:
            self._count += 1
            if self._count == 1:
                self._m = x  # seed the estimate with the first sample
                return
            q, rand = self._q, self._rng.random()
            if x > self._m and rand > 1.0 - q:
                self._step += 1.0 if self._sign > 0 else -1.0
                self._m += self._step if self._step > 0 else 1.0
                if self._m > x:
                    self._step += x - self._m
                    self._m = x
                if self._sign < 0 and self._step > 1:
                    self._step = 1.0
                self._sign = 1
            elif x < self._m and rand > q:
                self._step += 1.0 if self._sign < 0 else -1.0
                self._m -= self._step if self._step > 0 else 1.0
                if self._m < x:
                    self._step += self._m - x
                    self._m = x
                if self._sign > 0 and self._step > 1:
                    self._step = 1.0
                self._sign = -1

    def add_many(self, values: Any) -> None:
        try:
            iterator = iter(values)
        except TypeError as exc:
            raise FrugalError(values) from exc
        for v in iterator:
            self.add(v)

    # ── query ─────────────────────────────────────────────────────────────────────────
    def estimate(self) -> float:
        """Current estimate of the ``q``-quantile."""
        with self._lock:
            return self._m

    def reset(self, quantile: float | None = None, seed: int | None = None) -> None:
        """Clear the estimator; optionally reconfigure ``quantile`` / ``seed``."""
        with self._lock:
            nq = self._q if quantile is None else quantile
            ns = self._seed if seed is None else seed
            self._validate(nq, ns)
            self._q = float(nq)
            self._seed = ns
            self._init_state()

    def __len__(self) -> int:
        with self._lock:
            return self._count

    @property
    def quantile(self) -> float:
        return self._q

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def stats(self) -> dict:
        """Summary: ``quantile`` / ``estimate`` / ``step`` / ``count`` / ``seed``."""
        with self._lock:
            return {
                "quantile": self._q,
                "estimate": self._m,
                "step": self._step,
                "count": self._count,
                "seed": self._seed,
            }
