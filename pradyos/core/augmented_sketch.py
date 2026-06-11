"""Phase 104 — Sovereign Augmented Sketch / ASketch (Roy, Khan & Pomerantz, 2016).

A **two-stage frequency** estimator that bolts a small *exact* filter of the
current heavy hitters onto a sketch base — getting exact counts for the hot tail
and bounded-error estimates for everything else, far more accurately than the
sketch alone.

Stage 1 — **Count Sketch base** (Charikar–Chen–Farach-Colton 2002), *not*
Count-Min (P76). Each of ``depth`` rows maps an item to a bucket ``j`` and an
independent **sign** ``s ∈ {+1, -1}``; ``add`` does ``counter[d][j] += s · delta``.
The estimate is the **median** of ``s · counter[d][j]`` across the rows — a
*signed median*, so colliding items contribute ``±`` and cancel in expectation
(an *unbiased* estimate), where Count-Min's min only ever over-counts. This is
what lets the base shrug off a colliding hot item instead of inflating.

Stage 2 — **augmentation layer**: an exact-count dict of ≤ ``k`` items believed
heavy. On ``add``: if the item is in the dict, bump its exact count; otherwise
update the sketch and, if its sketch estimate now exceeds the smallest dict count
(the *k*-th largest), **promote** it — evicting the current minimum when the dict
is full. ``query`` returns the exact dict count when present, else the sketch
median; ``top_k`` reads straight off the dict (exact counts, descending).

Hashing is seeded BLAKE2b (the idiom of MinHash (P88) / Ribbon (P101) /
HeavyKeeper (P102)) — one digest per row split into a bucket index and a sign
bit. Pure stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any


class AugmentedSketchError(Exception):
    """Raised for an invalid Augmented-Sketch configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class AugmentedSketch:
    """Count Sketch base + exact top-K augmentation dict (two-stage frequency)."""

    def __init__(self, width: int = 1024, depth: int = 4, k: int = 10, seed: int = 0) -> None:
        self._validate(width, depth, k, seed)
        self._width = width
        self._depth = depth
        self._k = k
        self._seed = seed
        self._lock = threading.Lock()
        self._init_state()

    @staticmethod
    def _validate(width: Any, depth: Any, k: Any, seed: Any) -> None:
        if not _is_pos_int(width):
            raise AugmentedSketchError(width)
        if not _is_pos_int(depth):
            raise AugmentedSketchError(depth)
        if not _is_pos_int(k):
            raise AugmentedSketchError(k)
        if not _is_int(seed):
            raise AugmentedSketchError(seed)

    def _init_state(self) -> None:
        self._counter = [[0] * self._width for _ in range(self._depth)]
        self._exact: dict[Any, int] = {}  # augmentation layer (≤ k items)
        self._total = 0

    # ── hashing (pure) ────────────────────────────────────────────────────────────
    def _cell(self, row: int, item: Any) -> tuple[int, int]:
        digest = hashlib.blake2b(
            repr((self._seed, row, item)).encode("utf-8"), digest_size=16
        ).digest()
        bucket = int.from_bytes(digest[:8], "big") % self._width
        sign = 1 if (int.from_bytes(digest[8:], "big") & 1) else -1
        return bucket, sign

    # ── Count Sketch base ─────────────────────────────────────────────────────────
    def _add_to_sketch(self, item: Any, delta: int) -> None:
        for d in range(self._depth):
            j, s = self._cell(d, item)
            self._counter[d][j] += s * delta

    def _sketch_estimate(self, item: Any) -> int:
        vals = []
        for d in range(self._depth):
            j, s = self._cell(d, item)
            vals.append(s * self._counter[d][j])
        vals.sort()
        mid = self._depth // 2
        if self._depth % 2:
            median = vals[mid]
        else:
            median = (vals[mid - 1] + vals[mid]) / 2.0
        return max(0, round(median))

    # ── public API ─────────────────────────────────────────────────────────────────
    def add(self, item: Any, delta: int = 1) -> int:
        """Add ``delta`` occurrences of ``item``; return its updated estimate."""
        if not _is_pos_int(delta):
            raise AugmentedSketchError(delta)
        with self._lock:
            self._total += delta
            if item in self._exact:  # already tracked → exact increment
                self._exact[item] += delta
                return self._exact[item]
            self._add_to_sketch(item, delta)
            est = self._sketch_estimate(item)
            if len(self._exact) < self._k:  # room → promote
                self._exact[item] = est
            else:
                weakest = min(self._exact, key=self._exact.get)
                if est > self._exact[weakest]:  # beats the k-th largest → swap in
                    del self._exact[weakest]
                    self._exact[item] = est
            return self._exact.get(item, est)

    def query(self, item: Any) -> int:
        """Estimated frequency: exact dict count if tracked, else the Count Sketch median."""
        with self._lock:
            if item in self._exact:
                return self._exact[item]
            return self._sketch_estimate(item)

    def sketch_estimate(self, item: Any) -> int:
        """The Count Sketch base estimate (signed median), ignoring the augmentation dict."""
        with self._lock:
            return self._sketch_estimate(item)

    def top_k(self, n: int | None = None) -> list[tuple[Any, int]]:
        """The augmentation dict as ``(item, exact_count)`` sorted by count descending."""
        with self._lock:
            items = sorted(self._exact.items(), key=lambda kv: (-kv[1], repr(kv[0])))
        if n is None:
            n = self._k
        return items[:n]

    def reset(
        self,
        width: int | None = None,
        depth: int | None = None,
        k: int | None = None,
        seed: int | None = None,
    ) -> None:
        """Clear the sketch array and the augmentation dict; optionally reconfigure."""
        with self._lock:
            nw = self._width if width is None else width
            nd = self._depth if depth is None else depth
            nk = self._k if k is None else k
            ns = self._seed if seed is None else seed
            self._validate(nw, nd, nk, ns)
            self._width, self._depth, self._k, self._seed = nw, nd, nk, ns
            self._init_state()

    def __len__(self) -> int:
        with self._lock:
            return len(self._exact)

    @property
    def width(self) -> int:
        return self._width

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def k(self) -> int:
        return self._k

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``width`` / ``depth`` / ``k`` / ``seed``, plus ``tracked`` (items in the
        augmentation dict) and ``total`` (occurrences added)."""
        with self._lock:
            return {
                "width": self._width,
                "depth": self._depth,
                "k": self._k,
                "seed": self._seed,
                "tracked": len(self._exact),
                "total": self._total,
            }
