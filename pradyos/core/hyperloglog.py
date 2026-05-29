"""Phase 74 — Sovereign Cardinality Estimator (HyperLogLog).

Counts the number of *distinct* items in a stream using a fixed, tiny amount of
memory — independent of how many items flow through. Instead of storing the
items, it keeps ``m = 2^precision`` small registers; each item is hashed, the
top ``precision`` bits choose a register, and the register keeps the largest
"leading-zero rank" seen. Many items therefore share registers, so memory stays
flat while the estimate stays accurate to roughly ``1.04 / sqrt(m)`` (≈0.8% at
the default precision 14).

The estimate uses the standard bias-corrected harmonic-mean formula with linear-
counting for the small-cardinality range. Two sketches built independently can
be combined exactly via register-wise max (:meth:`merge`), which is what makes
HyperLogLog mergeable across shards.

Pure stdlib (``hashlib`` + ``math``); thread-safe via a single non-reentrant
``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Iterable

_MASK64 = (1 << 64) - 1


class HyperLogLog:
    """Probabilistic distinct-count sketch (stdlib only)."""

    def __init__(self, precision: int = 14) -> None:
        if not 4 <= precision <= 16:
            raise ValueError("precision must be between 4 and 16")
        self._p = precision
        self._m = 1 << precision
        self._alpha = self._alpha_for(self._m)
        self._registers = bytearray(self._m)
        self._lock = threading.Lock()

    @staticmethod
    def _alpha_for(m: int) -> float:
        if m == 16:
            return 0.673
        if m == 32:
            return 0.697
        if m == 64:
            return 0.709
        return 0.7213 / (1.0 + 1.079 / m)

    def _hash64(self, item) -> int:
        data = item.encode("utf-8") if isinstance(item, str) else repr(item).encode("utf-8")
        return int.from_bytes(hashlib.sha1(data).digest()[:8], "big")

    # ── mutation ──────────────────────────────────────────────────────────────
    def add(self, item) -> None:
        """Record an observation of ``item``."""
        h = self._hash64(item) & _MASK64
        idx = h >> (64 - self._p)                 # top p bits → register
        bits = 64 - self._p
        w = h & ((1 << bits) - 1)                 # remaining bits
        rank = (bits + 1) if w == 0 else (bits - w.bit_length() + 1)
        with self._lock:
            if rank > self._registers[idx]:
                self._registers[idx] = rank

    def add_many(self, items: Iterable) -> None:
        for item in items:
            self.add(item)

    def merge(self, other: "HyperLogLog") -> None:
        """Absorb ``other`` (register-wise max). Both must share precision."""
        if not isinstance(other, HyperLogLog) or other._p != self._p:
            raise ValueError("can only merge a HyperLogLog of the same precision")
        with other._lock:
            snapshot = bytes(other._registers)
        with self._lock:
            regs = self._registers
            for i in range(self._m):
                if snapshot[i] > regs[i]:
                    regs[i] = snapshot[i]

    def clear(self) -> None:
        """Reset to empty (estimate returns to 0)."""
        with self._lock:
            self._registers = bytearray(self._m)

    # ── estimation ──────────────────────────────────────────────────────────
    def _estimate_from(self, regs) -> float:
        m = self._m
        sum_inv = 0.0
        zeros = 0
        for r in regs:
            sum_inv += 1.0 / (1 << r)   # 2 ** (-r)
            if r == 0:
                zeros += 1
        estimate = self._alpha * m * m / sum_inv
        # Small-range correction: linear counting when many registers are empty.
        if estimate <= 2.5 * m and zeros > 0:
            estimate = m * math.log(m / zeros)
        return estimate

    def estimate(self) -> int:
        """Estimated number of distinct items added (rounded)."""
        with self._lock:
            regs = bytes(self._registers)
        return int(round(self._estimate_from(regs)))

    def __len__(self) -> int:
        return self.estimate()

    # ── introspection ─────────────────────────────────────────────────────────
    @property
    def precision(self) -> int:
        return self._p

    @property
    def registers(self) -> int:
        return self._m

    def fill_ratio(self) -> float:
        """Fraction of registers that are non-zero."""
        with self._lock:
            nonzero = sum(1 for r in self._registers if r)
            return nonzero / self._m

    def stats(self) -> dict:
        """JSON-serialisable snapshot of configuration and current estimate."""
        with self._lock:
            regs = bytes(self._registers)
        nonzero = sum(1 for r in regs if r)
        return {
            "precision": self._p,
            "registers": self._m,
            "estimate": int(round(self._estimate_from(regs))),
            "fill_ratio": round(nonzero / self._m, 6),
        }
