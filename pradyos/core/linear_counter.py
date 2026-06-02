"""Phase 112 — Sovereign Linear Counting (Whang, Vander-Zanden & Taylor, 1990).

*A linear-time probabilistic counting algorithm for database applications* — a
**cardinality** (distinct-count) estimator that is markedly more accurate than
HyperLogLog at *small-to-moderate* cardinalities, at the cost of more space.

The structure is a single **bitmap** of ``m`` bits, all initially 0. Each item is
hashed to one bit position ``h(x) mod m`` and that bit is set. Duplicates collapse
onto the same bit, so the bitmap depends only on the *distinct* items seen. After
the stream, the number of distinct items is estimated from the **fraction of bits
that are still zero**, ``V = zero_bits / m``:

    n̂ = −m · ln(V)

The derivation is the classic balls-in-bins expectation: each bit is zero iff none
of the ``n`` distinct items hashed to it, so ``E[zero_bits] = m·(1 − 1/m)^n ≈
m·e^(−n/m)``, hence ``E[V] ≈ e^(−n/m)`` and ``n ≈ −m·ln(V)``. Accuracy is excellent
while the bitmap is not close to full (load ``n/m`` up to ~10 with a suitably sized
``m``); once **every** bit is set, ``V = 0`` and the estimate is undefined — the
filter is *saturated* and :meth:`estimate` raises :class:`LinearCounterError`.

This is a *different* cardinality algorithm from the platform's HyperLogLog (P74 —
maximum leading-zero registers) and Theta sketch (P93 — KMV / k-minimum-values):
Linear Counting uses a bitmap and the empty-bin count rather than order statistics,
matching the project's one-algorithm-per-method pattern.

Hashing uses a single seeded BLAKE2b digest of the item (the stable, process-
independent idiom of MinHash (P88) / Counting Bloom (P107)); a running count of set
bits is kept so ``estimate`` is O(1). Pure stdlib (``hashlib``); thread-safe via a
single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any


class LinearCounterError(Exception):
    """Raised for an invalid Linear-Counter operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class LinearCounter:
    """Bitmap cardinality estimator — distinct count via the zero-bit fraction."""

    def __init__(self, num_bits: int = 65536, seed: int = 0) -> None:
        self._validate(num_bits, seed)
        self._m = num_bits
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    @staticmethod
    def _validate(num_bits: Any, seed: Any) -> None:
        if not _is_pos_int(num_bits):
            raise LinearCounterError(num_bits)
        if not _is_int(seed):
            raise LinearCounterError(seed)

    def _init_state(self) -> None:
        self._bitmap = bytearray((self._m + 7) // 8)
        self._bits_set = 0

    # ── hashing (pure) ───────────────────────────────────────────────────────────────
    def _position(self, item: Any) -> int:
        """Map an item to a single bit position in ``[0, m)`` (seeded BLAKE2b)."""
        data = repr((self._seed, item)).encode("utf-8")
        digest = hashlib.blake2b(data, digest_size=8).digest()
        return int.from_bytes(digest, "big") % self._m

    # ── public API ─────────────────────────────────────────────────────────────────────
    def add(self, item: Any) -> None:
        """Set ``item``'s bit. Duplicates are idempotent (distinct-count semantics)."""
        with self._lock:
            pos = self._position(item)
            byte, mask = pos >> 3, 1 << (pos & 7)
            if not (self._bitmap[byte] & mask):
                self._bitmap[byte] |= mask
                self._bits_set += 1

    def add_many(self, items: Any) -> None:
        """Add every item in an iterable."""
        try:
            iterator = iter(items)
        except TypeError as exc:
            raise LinearCounterError(items) from exc
        for item in iterator:
            self.add(item)

    def estimate(self) -> float:
        """Estimated distinct count ``−m·ln(V)``; raises if the bitmap is saturated."""
        with self._lock:
            return self._estimate_locked()

    def _estimate_locked(self) -> float:
        zero_bits = self._m - self._bits_set
        if zero_bits == 0:
            raise LinearCounterError("saturated: all bits set, cardinality estimate undefined")
        return -self._m * math.log(zero_bits / self._m)

    def reset(self, num_bits: int | None = None, seed: int | None = None) -> None:
        """Clear the bitmap; optionally reconfigure ``num_bits`` / ``seed``."""
        with self._lock:
            nm = self._m if num_bits is None else num_bits
            ns = self._seed if seed is None else seed
            self._validate(nm, ns)
            self._m, self._seed = nm, ns
            self._init_state()

    def __len__(self) -> int:
        """Number of bits set (≈ distinct items before collisions accumulate)."""
        with self._lock:
            return self._bits_set

    @property
    def num_bits(self) -> int:
        return self._m

    @property
    def bits_set(self) -> int:
        with self._lock:
            return self._bits_set

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def saturated(self) -> bool:
        with self._lock:
            return self._bits_set >= self._m

    def load_factor(self) -> float:
        """Fraction of bits set."""
        with self._lock:
            return round(self._bits_set / self._m, 6) if self._m else 0.0

    def stats(self) -> dict:
        """Summary: ``num_bits`` (m) / ``bits_set`` / ``zero_bits`` / ``load_factor`` /
        ``estimate`` (None if saturated) / ``seed``."""
        with self._lock:
            zero_bits = self._m - self._bits_set
            try:
                est: float | None = self._estimate_locked()
            except LinearCounterError:
                est = None
            return {
                "num_bits": self._m,
                "bits_set": self._bits_set,
                "zero_bits": zero_bits,
                "load_factor": round(self._bits_set / self._m, 6) if self._m else 0.0,
                "estimate": est,
                "seed": self._seed,
            }
