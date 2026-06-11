"""Phase 110 — Sovereign Stable Bloom Filter (Deng & Rafiei, SIGMOD 2006).

A Bloom variant for **unbounded data streams**. A classic Bloom (Phase 72) or even
a Counting Bloom (Phase 107) saturates on an endless stream — every cell eventually
fills, the false-positive rate climbs to 1, and the filter becomes useless. The
Stable Bloom Filter fixes this by **continuously forgetting**: it stores an array of
small ``d``-bit **cells** (each in ``0..Max`` where ``Max = 2^d - 1``) and, on *every*
insertion, first **decrements ``P`` uniformly-random cells** (floored at 0) before
**setting the element's ``k`` hashed cells to ``Max``**. The decrement step evicts
stale information at a constant rate, so the number of zero cells converges to a
non-zero steady state regardless of stream length — the fraction of set cells (and
hence the false-positive rate) **stabilises** instead of growing.

``contains`` reports membership when *every* one of an element's ``k`` cells is
``≥ 1``. Because a cell set by an element can later be decremented to 0 by a
subsequent insertion, the filter admits a small, **bounded false-negative** rate for
*old* elements (recently-inserted elements are recalled with high probability) — this
is the deliberate price for bounded memory on an infinite stream, and is exactly what
distinguishes it from the no-false-negative Bloom family.

``P`` (the decrement count) defaults to ``num_hashes · max_value``, the balance point
where the counter mass removed per insertion (``≈ P · fraction_nonzero``) matches the
mass added by setting ``k`` cells to ``Max`` — keeping the fill ratio stable below
saturation; it is tunable for a tighter false-positive vs false-negative trade-off
(Deng & Rafiei derive the optimal ``P`` from a target stable FP rate).

Cells are held one byte each in an ``array.array('B')`` (``Max ≤ 255``). Hashing uses
double-hashing ``h_i(x) = (h1(x) + i·h2(x)) mod m`` from one seeded BLAKE2b digest (the
stable, process-independent idiom of MinHash (P88) / Counting Bloom (P107)). The
probabilistic eviction draws from a ``random.Random(seed)`` instance, so a fixed seed
and insertion sequence reproduce the filter exactly. Pure stdlib (``array`` +
``hashlib`` + ``random``); thread-safe via a single ``threading.Lock`` (the eviction
RNG and cell array are mutated only under it).
"""

from __future__ import annotations

import array
import hashlib
import random
import threading
from typing import Any

_MAX_CELL_VALUE = 255  # one byte per cell


class StableBloomError(Exception):
    """Raised for an invalid Stable-Bloom operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class StableBloomFilter:
    """Streaming Bloom filter that forgets — stable FP rate, bounded FN rate."""

    def __init__(
        self,
        num_cells: int = 10000,
        num_hashes: int = 5,
        max_value: int = 3,
        decrement: int | None = None,
        seed: int = 0,
    ) -> None:
        self._validate(num_cells, num_hashes, max_value, decrement, seed)
        self._m = num_cells
        self._k = num_hashes
        self._max = max_value
        self._p = (
            self._default_decrement(num_hashes, max_value, num_cells)
            if decrement is None
            else decrement
        )
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    @staticmethod
    def _default_decrement(num_hashes: int, max_value: int, num_cells: int) -> int:
        """Balance point: mass removed ≈ mass added (k cells set to Max each insert)."""
        return max(1, min(num_hashes * max_value, num_cells))

    @staticmethod
    def _validate(
        num_cells: Any, num_hashes: Any, max_value: Any, decrement: Any, seed: Any
    ) -> None:
        if not _is_pos_int(num_cells):
            raise StableBloomError(num_cells)
        if not _is_pos_int(num_hashes):
            raise StableBloomError(num_hashes)
        if not _is_pos_int(max_value) or max_value > _MAX_CELL_VALUE:
            raise StableBloomError(max_value)
        if decrement is not None and not (_is_pos_int(decrement) and decrement <= num_cells):
            raise StableBloomError(decrement)
        if not _is_int(seed):
            raise StableBloomError(seed)

    def _init_state(self) -> None:
        self._cells = array.array("B", bytes(self._m))
        self._rng = random.Random(self._seed)
        self._count = 0

    # ── hashing (pure) ───────────────────────────────────────────────────────────────
    def _indices(self, element: Any) -> list[int]:
        """Double-hashing: ``(h1 + i·h2) mod m`` for ``i = 0..k-1`` from one seeded BLAKE2b digest."""
        data = repr((self._seed, element)).encode("utf-8")
        digest = hashlib.blake2b(data, digest_size=16).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:], "big") | 1  # force odd → full period under mod m
        return [(h1 + i * h2) % self._m for i in range(self._k)]

    # ── public API ─────────────────────────────────────────────────────────────────────
    def add(self, element: Any) -> None:
        """Add ``element``: evict ``P`` random cells (−1, floored at 0), then set its
        ``k`` hashed cells to ``Max``."""
        with self._lock:
            cells = self._cells
            m = self._m
            randrange = self._rng.randrange
            for _ in range(self._p):
                idx = randrange(m)
                if cells[idx] > 0:
                    cells[idx] -= 1
            for idx in self._indices(element):
                cells[idx] = self._max
            self._count += 1

    def contains(self, element: Any) -> bool:
        """True iff every one of ``element``'s ``k`` cells is ``≥ 1``."""
        with self._lock:
            return all(self._cells[idx] >= 1 for idx in self._indices(element))

    def __contains__(self, element: Any) -> bool:
        return self.contains(element)

    def __len__(self) -> int:
        with self._lock:
            return self._count

    def fill_ratio(self) -> float:
        """Fraction of non-zero cells — the stream-state metric that stabilises."""
        with self._lock:
            return self._fill_ratio_locked()

    def _fill_ratio_locked(self) -> float:
        if self._m == 0:
            return 0.0
        nonzero = sum(1 for c in self._cells if c > 0)
        return round(nonzero / self._m, 6)

    def reset(
        self,
        num_cells: int | None = None,
        num_hashes: int | None = None,
        max_value: int | None = None,
        decrement: int | None = None,
        seed: int | None = None,
    ) -> None:
        """Clear all cells; optionally reconfigure. Re-seeds the eviction RNG."""
        with self._lock:
            nc = self._m if num_cells is None else num_cells
            nk = self._k if num_hashes is None else num_hashes
            nmax = self._max if max_value is None else max_value
            # decrement=None here means "recompute the default for the new shape",
            # not "keep the old P" — the old P may be invalid for a smaller table.
            self._validate(nc, nk, nmax, decrement, ns := (self._seed if seed is None else seed))
            self._m, self._k, self._max, self._seed = nc, nk, nmax, ns
            self._p = self._default_decrement(nk, nmax, nc) if decrement is None else decrement
            self._init_state()

    @property
    def num_cells(self) -> int:
        return self._m

    @property
    def num_hashes(self) -> int:
        return self._k

    @property
    def max_value(self) -> int:
        return self._max

    @property
    def decrement(self) -> int:
        return self._p

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def count(self) -> int:
        """Number of ``add`` calls (the filter forgets, so this is not a live set size)."""
        with self._lock:
            return self._count

    def stats(self) -> dict:
        """Summary: ``num_cells`` (m) / ``num_hashes`` (k) / ``max_value`` (Max) /
        ``decrement`` (P) / ``count`` (adds) / ``fill_ratio`` / ``seed``."""
        with self._lock:
            return {
                "num_cells": self._m,
                "num_hashes": self._k,
                "max_value": self._max,
                "decrement": self._p,
                "count": self._count,
                "fill_ratio": self._fill_ratio_locked(),
                "seed": self._seed,
            }
