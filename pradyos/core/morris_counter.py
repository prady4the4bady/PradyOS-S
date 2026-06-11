"""Phase 111 — Sovereign Morris Counter (Morris, 1978).

*Counting large numbers of events in small registers* — the original **approximate
counting** algorithm. To count up to ``n`` events exactly takes ``⌈log₂ n⌉`` bits;
the Morris counter instead stores only a small **exponent register** ``c`` and reaches
an estimate of ``n`` using just ``≈ log₂ log₂ n`` bits, by incrementing ``c`` only
*probabilistically*.

Algorithm (generalised base ``a > 1``; Flajolet 1985):

    increment:  with probability  a^(-c)   set  c ← c + 1     (else leave c unchanged)
    estimate:   n̂ = (a^c − 1) / (a − 1)

The estimate is **unbiased** — ``E[n̂] = n`` for all ``n`` — which follows by induction:
``E[a^c]`` rises by exactly ``(a − 1)`` per event, so after ``n`` events
``E[a^c] = 1 + n·(a − 1)`` and ``E[(a^c − 1)/(a − 1)] = n``. For the classic **base-2**
counter this is the familiar ``increment with prob 2^(-c)``, ``n̂ = 2^c − 1``.

The base ``a`` trades memory for accuracy: the variance is ``≈ n·(n − 1)·(a − 1)/2``,
so a base near ``1`` is very accurate but the register grows almost as fast as an exact
counter, while a larger base keeps the register tiny at the cost of higher variance.

This is a distinct feature-class from the platform's **cardinality** sketches
(HyperLogLog/P74 — count *distinct* items) and its **frequency** sketches
(Count-Min/P76, Count-Sketch/P94 — per-key counts): the Morris counter estimates a
single running **event total**.

The compact state is the single integer ``register`` (``c``); an exact ``increments``
tally is also kept purely so ``stats`` / ``relative_error`` can report observed
accuracy — a memory-constrained deployment would omit it. The probabilistic coin is a
``random.Random(seed)`` instance, so a fixed seed and increment sequence reproduce the
counter exactly. Pure stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import random
import threading
from typing import Any


class MorrisCounterError(Exception):
    """Raised for an invalid Morris-counter operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class MorrisCounter:
    """Probabilistic approximate counter — counts to ``n`` in ``≈ log₂ log₂ n`` bits."""

    def __init__(self, base: float = 2.0, seed: int = 0) -> None:
        self._validate(base, seed)
        self._base = float(base)
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    @staticmethod
    def _validate(base: Any, seed: Any) -> None:
        if not (_is_number(base) and base > 1.0):
            raise MorrisCounterError(base)
        if not _is_int(seed):
            raise MorrisCounterError(seed)

    def _init_state(self) -> None:
        self._c = 0  # the compact exponent register
        self._increments = 0  # exact tally (auxiliary — for accuracy reporting only)
        self._rng = random.Random(self._seed)

    # ── public API ─────────────────────────────────────────────────────────────────────
    def increment(self, times: int = 1) -> int:
        """Register ``times`` events; bump the register with probability ``base^(-c)`` each.

        Returns the resulting register value ``c``."""
        if not (_is_int(times) and times >= 1):
            raise MorrisCounterError(times)
        with self._lock:
            random_fn = self._rng.random
            base = self._base
            c = self._c
            for _ in range(times):
                if random_fn() < base ** (-c):
                    c += 1
            self._c = c
            self._increments += times
            return c

    def estimate(self) -> float:
        """Unbiased estimate of the number of events: ``(base^c − 1) / (base − 1)``."""
        with self._lock:
            return self._estimate_locked()

    def _estimate_locked(self) -> float:
        return (self._base**self._c - 1.0) / (self._base - 1.0)

    def relative_error(self) -> float:
        """``|estimate − increments| / increments`` (0.0 before any increment)."""
        with self._lock:
            if self._increments == 0:
                return 0.0
            return abs(self._estimate_locked() - self._increments) / self._increments

    def reset(self, base: float | None = None, seed: int | None = None) -> None:
        """Clear the register; optionally reconfigure ``base`` / ``seed`` (re-seeds the RNG)."""
        with self._lock:
            nb = self._base if base is None else base
            ns = self._seed if seed is None else seed
            self._validate(nb, ns)
            self._base = float(nb)
            self._seed = ns
            self._init_state()

    @property
    def register(self) -> int:
        """The compact exponent state ``c`` (this is the whole stored counter)."""
        with self._lock:
            return self._c

    @property
    def increments(self) -> int:
        """Exact number of events registered (auxiliary — not part of the compact state)."""
        with self._lock:
            return self._increments

    @property
    def base(self) -> float:
        return self._base

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``register`` (c) / ``estimate`` / ``increments`` (true n) /
        ``base`` / ``relative_error`` / ``seed``."""
        with self._lock:
            est = self._estimate_locked()
            rel = 0.0 if self._increments == 0 else abs(est - self._increments) / self._increments
            return {
                "register": self._c,
                "estimate": est,
                "increments": self._increments,
                "base": self._base,
                "relative_error": rel,
                "seed": self._seed,
            }
