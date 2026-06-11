"""Phase 102 — Sovereign HeavyKeeper (Gong et al., 2018).

A probabilistic **heavy-hitter / top-K** sketch. Where Count-Min (P76) keeps a
plain counter grid and reports the *minimum* matching counter, and Space-Saving
(P87) evicts the *minimum* monitored counter, HeavyKeeper's signature is
**exponential-decay-on-collision**: a colliding (wrong) item only chips away at a
resident counter with probability ``decay ** -count`` — so a genuine heavy hitter,
whose count is large, is almost never decayed, while cold items evaporate fast.
This count-with-decay rule is what makes the estimate accurate for the heavy tail
while using sub-linear space.

Structure: a ``depth × width`` grid of ``(fingerprint, count)`` buckets
(``count == 0`` marks an empty bucket). For each incoming occurrence of an item
``x`` (fingerprint ``f = fp(x)``), every row ``d`` hashes ``x`` to a bucket ``j``:

  * empty bucket            → claim it: ``(f, 1)``;
  * fingerprint matches     → ``count += 1``;
  * fingerprint differs     → with probability ``decay ** -count`` do ``count -= 1``,
                              and if it hits 0 the bucket is **evicted** and
                              re-claimed by ``x`` as ``(f, 1)``.

The frequency estimate is the **max** matching counter across the rows (not the
min, as in Count-Min) — decay makes over-counting the failure mode to guard, so
the largest surviving counter is the best estimate. A bounded **min-heap of size
k** (indexed, with ``O(log k)`` updates) tracks the current top-K: after each
add, the item's fresh estimate is reconciled into the heap — replacing the heap
minimum only when it is exceeded.

Hashing is seeded BLAKE2b (the idiom of MinHash (P88) / Count Sketch (P94) /
Ribbon (P101)); the probabilistic decay draws from a seeded ``random.Random`` so
a given ``seed`` + stream is fully deterministic. Pure stdlib; thread-safe via a
single ``threading.Lock`` (every public mutator/reader runs under it).
"""

from __future__ import annotations

import hashlib
import random
import threading
from typing import Any

_FP_MASK = (1 << 32) - 1  # 32-bit fingerprints → ~2**-32 collision per bucket


class HeavyKeeperError(Exception):
    """Raised for an invalid HeavyKeeper configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class HeavyKeeper:
    """Probabilistic top-K heavy-hitter sketch with exponential-decay eviction."""

    def __init__(
        self, k: int = 10, width: int = 1024, depth: int = 4, decay: float = 1.08, seed: int = 0
    ) -> None:
        self._validate(k, width, depth, decay, seed)
        self._k = k
        self._width = width
        self._depth = depth
        self._decay = float(decay)
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    # ── validation ────────────────────────────────────────────────────────────────
    @staticmethod
    def _validate(k: Any, width: Any, depth: Any, decay: Any, seed: Any) -> None:
        if not _is_pos_int(k):
            raise HeavyKeeperError(k)
        if not _is_pos_int(width):
            raise HeavyKeeperError(width)
        if not _is_pos_int(depth):
            raise HeavyKeeperError(depth)
        if isinstance(decay, bool) or not isinstance(decay, int | float) or decay <= 1.0:
            raise HeavyKeeperError(decay)  # decay must be > 1 for a valid decay prob
        if not _is_int(seed):
            raise HeavyKeeperError(seed)

    def _init_state(self) -> None:
        self._fp = [[0] * self._width for _ in range(self._depth)]
        self._cnt = [[0] * self._width for _ in range(self._depth)]
        self._heap: list[list] = []  # indexed min-heap of [count, item]
        self._pos: dict[Any, int] = {}  # item -> heap index
        self._total = 0
        self._rng = random.Random(self._seed)

    # ── hashing (pure) ────────────────────────────────────────────────────────────
    def _digest(self, tag: Any, item: Any) -> int:
        data = repr((self._seed, tag, item)).encode("utf-8")
        return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")

    def _fingerprint(self, item: Any) -> int:
        return self._digest("fp", item) & _FP_MASK

    def _bucket(self, row: int, item: Any) -> int:
        return self._digest(row, item) % self._width

    # ── indexed min-heap (by count) ────────────────────────────────────────────────
    def _swap(self, i: int, j: int) -> None:
        h = self._heap
        h[i], h[j] = h[j], h[i]
        self._pos[h[i][1]] = i
        self._pos[h[j][1]] = j

    def _sift_up(self, i: int) -> None:
        h = self._heap
        while i > 0:
            parent = (i - 1) // 2
            if h[i][0] < h[parent][0]:
                self._swap(i, parent)
                i = parent
            else:
                break

    def _sift_down(self, i: int) -> None:
        h = self._heap
        n = len(h)
        while True:
            smallest = i
            left = 2 * i + 1
            right = 2 * i + 2
            if left < n and h[left][0] < h[smallest][0]:
                smallest = left
            if right < n and h[right][0] < h[smallest][0]:
                smallest = right
            if smallest == i:
                break
            self._swap(i, smallest)
            i = smallest

    def _heap_update(self, item: Any, est: int) -> None:
        if item in self._pos:  # already tracked → re-key
            i = self._pos[item]
            self._heap[i][0] = est
            self._sift_up(i)
            self._sift_down(i)
        elif len(self._heap) < self._k:  # room → insert
            self._heap.append([est, item])
            i = len(self._heap) - 1
            self._pos[item] = i
            self._sift_up(i)
        elif est > self._heap[0][0]:  # beats the weakest → replace min
            old = self._heap[0][1]
            del self._pos[old]
            self._heap[0] = [est, item]
            self._pos[item] = 0
            self._sift_down(0)

    # ── core add (one occurrence) ──────────────────────────────────────────────────
    def _add_one(self, item: Any, fp: int) -> None:
        for d in range(self._depth):
            j = self._bucket(d, item)
            c = self._cnt[d][j]
            if c == 0:
                self._fp[d][j] = fp
                self._cnt[d][j] = 1
            elif self._fp[d][j] == fp:
                self._cnt[d][j] = c + 1
            else:
                # exponential-decay eviction: P(decrement) = decay ** -count
                if self._rng.random() < self._decay ** (-c):
                    self._cnt[d][j] = c - 1
                    if c - 1 == 0:
                        self._fp[d][j] = fp
                        self._cnt[d][j] = 1

    def _estimate(self, item: Any, fp: int) -> int:
        best = 0
        for d in range(self._depth):
            j = self._bucket(d, item)
            if self._cnt[d][j] > best and self._fp[d][j] == fp:
                best = self._cnt[d][j]
        return best

    # ── public API ─────────────────────────────────────────────────────────────────
    def add(self, item: Any, count: int = 1) -> int:
        """Add ``count`` occurrences of ``item``; return its updated estimate."""
        if not _is_pos_int(count):
            raise HeavyKeeperError(count)
        with self._lock:
            fp = self._fingerprint(item)
            for _ in range(count):
                self._add_one(item, fp)
            self._total += count
            est = self._estimate(item, fp)
            self._heap_update(item, est)
            return est

    def query(self, item: Any) -> int:
        """Estimated frequency of ``item`` (max matching counter across rows; 0 if absent)."""
        with self._lock:
            return self._estimate(item, self._fingerprint(item))

    def top_k(self, n: int | None = None) -> list[tuple[Any, int]]:
        """The tracked heavy hitters as ``(item, estimate)`` sorted by estimate descending."""
        with self._lock:
            items = [
                (item, self._estimate(item, self._fingerprint(item))) for _, item in self._heap
            ]
        items.sort(key=lambda kv: (-kv[1], repr(kv[0])))
        if n is None:
            n = self._k
        return items[:n]

    def reset(
        self,
        k: int | None = None,
        width: int | None = None,
        depth: int | None = None,
        decay: float | None = None,
        seed: int | None = None,
    ) -> None:
        """Clear all buckets and the heap; optionally reconfigure before reallocating."""
        with self._lock:
            nk = self._k if k is None else k
            nw = self._width if width is None else width
            nd = self._depth if depth is None else depth
            ndec = self._decay if decay is None else decay
            ns = self._seed if seed is None else seed
            self._validate(nk, nw, nd, ndec, ns)
            self._k, self._width, self._depth, self._decay, self._seed = nk, nw, nd, float(ndec), ns
            self._init_state()

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)

    @property
    def k(self) -> int:
        return self._k

    @property
    def width(self) -> int:
        return self._width

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def decay(self) -> float:
        return self._decay

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``k`` / ``width`` / ``depth`` / ``decay`` / ``seed``, plus ``tracked``
        (items currently in the top-K heap) and ``total`` (occurrences added)."""
        with self._lock:
            return {
                "k": self._k,
                "width": self._width,
                "depth": self._depth,
                "decay": self._decay,
                "seed": self._seed,
                "tracked": len(self._heap),
                "total": self._total,
            }
