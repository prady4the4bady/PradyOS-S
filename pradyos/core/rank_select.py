"""Phase 134 — Sovereign Rank/Select succinct bitvector (Jacobson, 1989).

The **foundational succinct-data-structure primitive** — `O(1)` ``rank`` and fast ``select``
over a *static* bit array with `o(n)` extra index bits — a new capability for the platform.
Every succinct structure (wavelet trees, succinct tries, balanced-parenthesis trees) is built
on these two operations:

  * ``rank1(i)`` — the number of set bits in ``bits[0..i)`` (with ``rank0`` the dual);
  * ``select1(k)`` — the position of the ``k``-th set bit (1-indexed; ``select0`` the dual).

The bits are packed into 64-bit words. A classic **two-level** index precomputes, for each
**superblock** (`S = 8` words = 512 bits), the absolute number of set bits before it, and for
each **block** (one word) the number of set bits before it *within its superblock*. ``rank1``
is then a superblock lookup + a block lookup + one partial-word ``int.bit_count`` — **constant
time**. ``select`` **binary-searches the cumulative rank** (`O(log n)`), which the `O(1)` rank
makes cheap. The extra index is `o(n)` bits (relative block counts are ≤ 512).

This is *exact and deterministic* — distinct from the platform's approximate frequency
sketches (Count-Min/P76, Count-Sketch/P94, …): rank/select is a precise index over a known
bit array, not an estimator. Pure stdlib (``int.bit_count``, Python ≥ 3.10); thread-safe via a
single ``threading.Lock``; static (built once from the bit array, then queried).
"""

from __future__ import annotations

import threading
from typing import Any

_W = 64  # bits per word
_S = 8  # words per superblock (512 bits)


class RankSelectError(Exception):
    """Raised for an invalid Rank/Select operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class RankSelect:
    """Static succinct bitvector with O(1) rank and O(log n) select (two-level index)."""

    def __init__(self, bits: Any = None) -> None:
        self._lock = threading.Lock()
        self._build("" if bits is None else bits)

    # ── build ──────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _normalise(bits: Any) -> list:
        """Coerce ``bits`` (a 0/1 string, or an iterable of 0/1/bool) to a list of 0/1 ints."""
        if isinstance(bits, str):
            out = []
            for ch in bits:
                if ch not in ("0", "1"):
                    raise RankSelectError(f"bit string may contain only '0'/'1', got {ch!r}")
                out.append(1 if ch == "1" else 0)
            return out
        try:
            seq = list(bits)
        except TypeError as exc:
            raise RankSelectError("bits must be a 0/1 string or an iterable of 0/1") from exc
        out = []
        for b in seq:
            if isinstance(b, bool):
                out.append(1 if b else 0)
            elif isinstance(b, int) and b in (0, 1):
                out.append(b)
            else:
                raise RankSelectError(f"each bit must be 0 or 1, got {b!r}")
        return out

    def _build_locked(self, bits: Any) -> None:
        arr = self._normalise(bits)
        n = len(arr)
        nwords = (n + _W - 1) // _W
        words = [0] * nwords
        for i, b in enumerate(arr):
            if b:
                words[i >> 6] |= 1 << (i & 63)  # bit i at position (i mod 64), LSB-first

        nsb = (nwords + _S - 1) // _S
        superblock_cum = [0] * (nsb + 1)  # set bits before each superblock
        block_rel = [0] * nwords  # set bits before this word within its superblock
        total = 0
        for sb in range(nsb):
            superblock_cum[sb] = total
            rel = 0
            for j in range(_S):
                w = sb * _S + j
                if w >= nwords:
                    break
                block_rel[w] = rel
                pc = words[w].bit_count()
                rel += pc
                total += pc
        superblock_cum[nsb] = total

        self._n = n
        self._words = words
        self._nwords = nwords
        self._superblock_cum = superblock_cum
        self._block_rel = block_rel
        self._count1 = total

    def _build(self, bits: Any) -> None:
        with self._lock:
            self._build_locked(bits)

    def build(self, bits: Any) -> None:
        """(Re)build the bitvector from ``bits`` (static — replaces any prior contents)."""
        with self._lock:
            self._build_locked(bits)

    # ── rank (O(1)) ────────────────────────────────────────────────────────────────────
    def _rank1_locked(self, i: int) -> int:
        if i <= 0:
            return 0
        if i >= self._n:
            return self._count1
        w = i >> 6
        off = i & 63
        return (
            self._superblock_cum[w // _S]
            + self._block_rel[w]
            + (self._words[w] & ((1 << off) - 1)).bit_count()
        )

    def rank1(self, i: int) -> int:
        """Number of set bits in ``bits[0..i)`` (``i`` in ``[0, n]``)."""
        if not isinstance(i, int) or isinstance(i, bool):
            raise RankSelectError("i must be an int")
        with self._lock:
            if not (0 <= i <= self._n):
                raise RankSelectError(f"i must be an int in [0, {self._n}]")
            return self._rank1_locked(i)

    def rank0(self, i: int) -> int:
        """Number of clear bits in ``bits[0..i)`` (``i`` in ``[0, n]``)."""
        if not isinstance(i, int) or isinstance(i, bool):
            raise RankSelectError("i must be an int")
        with self._lock:
            if not (0 <= i <= self._n):
                raise RankSelectError(f"i must be an int in [0, {self._n}]")
            return i - self._rank1_locked(i)

    # ── select (O(log n) — binary search on the cumulative rank) ──────────────────────
    def select1(self, k: int) -> int:
        """Position of the ``k``-th set bit (1-indexed); raises if ``k`` ∉ ``[1, count1]``."""
        if not isinstance(k, int) or isinstance(k, bool):
            raise RankSelectError("k must be an int")
        with self._lock:
            if not (1 <= k <= self._count1):
                raise RankSelectError(f"k must be in [1, {self._count1}]")
            lo, hi = 0, self._n - 1
            while lo < hi:  # smallest p with rank1(p+1) >= k
                mid = (lo + hi) >> 1
                if self._rank1_locked(mid + 1) >= k:
                    hi = mid
                else:
                    lo = mid + 1
            return lo

    def select0(self, k: int) -> int:
        """Position of the ``k``-th clear bit (1-indexed); raises if ``k`` ∉ ``[1, count0]``."""
        if not isinstance(k, int) or isinstance(k, bool):
            raise RankSelectError("k must be an int")
        with self._lock:
            count0 = self._n - self._count1
            if not (1 <= k <= count0):
                raise RankSelectError(f"k must be in [1, {count0}]")
            lo, hi = 0, self._n - 1
            while lo < hi:  # smallest p with rank0(p+1) >= k
                mid = (lo + hi) >> 1
                if (mid + 1) - self._rank1_locked(mid + 1) >= k:
                    hi = mid
                else:
                    lo = mid + 1
            return lo

    # ── access / introspection ──────────────────────────────────────────────────────────
    def get(self, i: int) -> int:
        """The bit at position ``i`` (``0`` or ``1``); ``i`` in ``[0, n)``."""
        if not isinstance(i, int) or isinstance(i, bool):
            raise RankSelectError("i must be an int")
        with self._lock:
            if not (0 <= i < self._n):
                raise RankSelectError(f"i must be an int in [0, {self._n - 1}]")
            return (self._words[i >> 6] >> (i & 63)) & 1

    def reset(self) -> None:
        """Empty the bitvector."""
        with self._lock:
            self._build_locked("")

    def __len__(self) -> int:
        return self._n

    @property
    def size(self) -> int:
        return self._n

    @property
    def count1(self) -> int:
        return self._count1

    @property
    def count0(self) -> int:
        return self._n - self._count1

    def stats(self) -> dict:
        """Summary: ``size`` / ``count1`` / ``count0`` / ``num_words`` / ``num_superblocks``."""
        with self._lock:
            return {
                "size": self._n,
                "count1": self._count1,
                "count0": self._n - self._count1,
                "num_words": self._nwords,
                "num_superblocks": (self._nwords + _S - 1) // _S,
            }
