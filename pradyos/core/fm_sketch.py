"""Phase 129 — Sovereign Flajolet–Martin / PCSA cardinality sketch (Flajolet & Martin, 1985).

*Probabilistic Counting with Stochastic Averaging* — the **original distinct-count
estimator** and the progenitor of every later cardinality sketch on the platform. A new
mechanism for the platform: it estimates ``|{distinct items}|`` from **bit patterns**, not
registers or min-hashes.

Mechanism. Each item is hashed to a uniform 64-bit value. The **trailing-zero count** ``ρ``
of the (low) hash bits is geometric — ``P(ρ = i) = 2^−(i+1)`` — so setting bit ``ρ`` of a
bitmap leaves a tell-tale "all low bits eventually set" pattern whose frontier tracks
``log₂`` of the number of distinct items. The **lowest unset bit** ``R`` of the bitmap then
satisfies ``E[R] ≈ log₂(φ · n)`` with ``φ ≈ 0.77351`` (the Flajolet–Martin constant), giving
``n ≈ 2^R / φ`` from a single bitmap.

**Stochastic averaging** (the *SA* in PCSA) cuts the variance: a leading hash prefix routes
each item to one of ``m`` bitmaps, the rest gives ``ρ``; averaging the ``m`` lowest-unset
positions ``A = (1/m) Σ R_j`` yields the estimate ``n̂ = (m / φ) · 2^A`` with standard error
``≈ 0.78 / √m``. Sketches are **mergeable** by OR-ing the bitmaps.

This is *different* from the platform's other cardinality sketches: HyperLogLog/P74 (harmonic
mean of *max*-leading-zero registers), Theta/P93 (KMV min-hashes), Linear Counting (bit-array
fill ratio), HyperMinHash/P117 — FM/PCSA is the bit-pattern-observable original they descend
from. Like the original, it is accurate for ``n ≳ m`` and **overestimates very small
cardinalities** (the classic small-range bias); the empty sketch reports exactly ``0``.
Pure stdlib (``hashlib.blake2b``); thread-safe via a single ``threading.Lock``; deterministic
given the seed.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any, Iterable

# Flajolet–Martin magic constant φ (correction for the lowest-unset-bit estimator).
_PHI = 0.7735162909

_HASH_BITS = 64
_HASH_MASK = (1 << _HASH_BITS) - 1


class FMSketchError(Exception):
    """Raised for an invalid FM-sketch operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_pow2(x: Any) -> bool:
    return _is_int(x) and x >= 1 and (x & (x - 1)) == 0


class FMSketch:
    """Flajolet–Martin / PCSA probabilistic distinct-count sketch."""

    def __init__(self, num_bitmaps: int = 64, num_bits: int = 32, seed: int = 0) -> None:
        self._validate(num_bitmaps, num_bits, seed)
        self._m = num_bitmaps
        self._p_bits = num_bitmaps.bit_length() - 1     # log2(m); m is a power of two
        self._num_bits = num_bits
        self._seed = seed
        self._seed_bytes = repr(seed).encode("ascii")
        self._lock = threading.Lock()
        self._bitmaps = [0] * num_bitmaps

    # ── validation / hashing ─────────────────────────────────────────────────────────
    @staticmethod
    def _validate(num_bitmaps: Any, num_bits: Any, seed: Any) -> None:
        if not _is_pow2(num_bitmaps) or num_bitmaps > 65536:
            raise FMSketchError("num_bitmaps must be a power of two in [1, 65536]")
        if not _is_int(num_bits) or not (1 <= num_bits <= 32):
            raise FMSketchError("num_bits must be an int in [1, 32]")
        if not _is_int(seed):
            raise FMSketchError("seed must be an int")

    @staticmethod
    def _to_bytes(item: Any) -> bytes:
        if isinstance(item, bool):
            raise FMSketchError("item must be str, bytes or int (not bool)")
        if isinstance(item, bytes):
            return b"b" + item
        if isinstance(item, str):
            return b"s" + item.encode("utf-8")
        if isinstance(item, int):
            return b"i" + repr(item).encode("ascii")
        raise FMSketchError("item must be str, bytes or int")

    def _hash(self, item: Any) -> int:
        digest = hashlib.blake2b(self._seed_bytes + self._to_bytes(item), digest_size=8).digest()
        return int.from_bytes(digest, "big") & _HASH_MASK

    # ── update ────────────────────────────────────────────────────────────────────────
    def _add_hash(self, h: int) -> None:
        bucket = h >> (_HASH_BITS - self._p_bits)                 # top p_bits → which bitmap
        w = h & ((1 << (_HASH_BITS - self._p_bits)) - 1)          # remaining bits → ρ
        if w == 0:
            rho = _HASH_BITS - self._p_bits
        else:
            rho = (w & -w).bit_length() - 1                       # trailing-zero count
        if rho >= self._num_bits:
            rho = self._num_bits - 1                              # cap to the bitmap width
        self._bitmaps[bucket] |= 1 << rho

    def add(self, item: Any) -> None:
        """Observe one item (idempotent in the distinct-count sense)."""
        h = self._hash(item)
        with self._lock:
            self._add_hash(h)

    def add_many(self, items: Iterable[Any]) -> int:
        """Observe many items; returns the number consumed."""
        hashes = [self._hash(it) for it in items]                # hash outside the lock
        with self._lock:
            for h in hashes:
                self._add_hash(h)
        return len(hashes)

    # ── estimation ──────────────────────────────────────────────────────────────────
    def _lowest_unset_bit(self, bitmap: int) -> int:
        i = 0
        nb = self._num_bits
        while i < nb and (bitmap >> i) & 1:
            i += 1
        return i

    def _estimate_locked(self) -> float:
        if not any(self._bitmaps):
            return 0.0                                            # empty sketch → exactly 0
        total = sum(self._lowest_unset_bit(b) for b in self._bitmaps)
        a = total / self._m
        return (self._m / _PHI) * (2.0 ** a)

    def estimate(self) -> float:
        """Estimated number of distinct items observed."""
        with self._lock:
            return self._estimate_locked()

    def count(self) -> int:
        """Estimated distinct count, rounded to an int."""
        return int(round(self.estimate()))

    def __len__(self) -> int:
        return self.count()

    # ── merge ─────────────────────────────────────────────────────────────────────────
    def merge(self, other: "FMSketch") -> None:
        """Fold ``other`` into ``self`` by OR-ing the bitmaps (configs must match)."""
        if not isinstance(other, FMSketch):
            raise FMSketchError("can only merge another FMSketch")
        if (other._m, other._num_bits, other._seed) != (self._m, self._num_bits, self._seed):
            raise FMSketchError("cannot merge sketches with different num_bitmaps/num_bits/seed")
        with self._lock:
            snapshot = list(other._bitmaps) if other is not self else self._bitmaps[:]
            for i, b in enumerate(snapshot):
                self._bitmaps[i] |= b

    def reset(self, num_bitmaps: int | None = None, num_bits: int | None = None,
              seed: int | None = None) -> None:
        """Clear all bitmaps; optionally reconfigure ``num_bitmaps`` / ``num_bits`` / ``seed``."""
        with self._lock:
            nm = self._m if num_bitmaps is None else num_bitmaps
            nb = self._num_bits if num_bits is None else num_bits
            ns = self._seed if seed is None else seed
            self._validate(nm, nb, ns)
            self._m = nm
            self._p_bits = nm.bit_length() - 1
            self._num_bits = nb
            self._seed = ns
            self._seed_bytes = repr(ns).encode("ascii")
            self._bitmaps = [0] * nm

    # ── introspection ──────────────────────────────────────────────────────────────────
    @property
    def num_bitmaps(self) -> int:
        return self._m

    @property
    def num_bits(self) -> int:
        return self._num_bits

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def standard_error(self) -> float:
        """Relative standard error of the estimate, ``≈ 0.78 / √m``."""
        return 0.78 / (self._m ** 0.5)

    def stats(self) -> dict:
        """Summary: ``num_bitmaps`` / ``num_bits`` / ``estimate`` / ``standard_error`` / ``seed``."""
        with self._lock:
            est = self._estimate_locked()
        return {
            "num_bitmaps": self._m,
            "num_bits": self._num_bits,
            "estimate": round(est, 4),
            "standard_error": round(0.78 / (self._m ** 0.5), 6),
            "seed": self._seed,
        }
