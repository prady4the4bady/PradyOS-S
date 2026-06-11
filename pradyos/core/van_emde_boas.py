"""Phase 152 — Sovereign van Emde Boas Tree (van Emde Boas, 1975).

A **bounded-integer ordered set** over a universe `[0, U)` (`U` rounded up to a power of two)
supporting `insert` / `delete` / `member` / `minimum` / `maximum` and — most distinctively —
**`successor` / `predecessor` in `O(log log U)`**. That complexity class is new to the platform:
no comparison-ordered set or hash/sketch here answers "next larger integer present" sub-`O(log
n)`. It is also the platform's first *integer-universe* (van-Emde-Boas-recursion) structure.

Each node of universe `u` recurses into a `√u` **summary** vEB (which clusters are non-empty) plus
up to `√u` **cluster** vEBs (the low bits), with the running **min stored lazily** — the minimum
is held *outside* its cluster, so every operation makes only one deep recursive call, giving the
`O(log log U)` recurrence `T(u) = T(√u) + O(1)`.

The recursion is carried by an internal, lock-free :class:`_VEBNode`; the public
:class:`VanEmdeBoas` wraps the root with a single ``threading.Lock`` (so recursive descent never
re-enters the lock), validates inputs, and tracks ``size``. Clusters/summaries are created lazily,
keeping memory `O(n)` rather than `O(U)`. **Recursion depth is `O(log log U)` — at most ~5 for a
`2^32` universe — and is structurally bounded (never input-dependent), so recursion is safe here.**
Pure stdlib; deterministic.
"""

from __future__ import annotations

import threading
from typing import Any


class VanEmdeBoasError(Exception):
    """Raised for an invalid van-Emde-Boas operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _round_pow2(u: int) -> int:
    if u < 2:
        return 2
    p = 1
    while p < u:
        p <<= 1
    return p


class _VEBNode:
    """Lock-free recursive vEB node over universe ``u`` (a power of two)."""

    __slots__ = ("u", "lb", "lower", "upper", "min", "max", "summary", "clusters")

    def __init__(self, u: int) -> None:
        self.u = u
        self.min: int | None = None
        self.max: int | None = None
        if u <= 2:
            self.lb = 0
            self.lower = 0
            self.upper = 0
            self.summary: _VEBNode | None = None
            self.clusters = None
        else:
            k = u.bit_length() - 1  # u == 2**k
            self.lb = k // 2
            self.lower = 1 << self.lb  # cluster universe
            self.upper = u >> self.lb  # number of clusters = summary universe
            self.summary = None  # created lazily
            self.clusters: dict[int, _VEBNode] = {}

    def high(self, x: int) -> int:
        return x >> self.lb

    def low(self, x: int) -> int:
        return x & (self.lower - 1)

    def index(self, h: int, l: int) -> int:
        return (h << self.lb) | l

    def _cluster(self, h: int) -> _VEBNode:
        c = self.clusters.get(h)
        if c is None:
            c = _VEBNode(self.lower)
            self.clusters[h] = c
        return c

    def _summary(self) -> _VEBNode:
        if self.summary is None:
            self.summary = _VEBNode(self.upper)
        return self.summary

    # ── membership ─────────────────────────────────────────────────────────────────────
    def member(self, x: int) -> bool:
        if x == self.min or x == self.max:
            return True
        if self.u <= 2:
            return False
        c = self.clusters.get(self.high(x))
        return c is not None and c.member(self.low(x))

    # ── insert (returns True iff newly added) ────────────────────────────────────────────
    def insert(self, x: int) -> bool:
        if self.u == 2:
            if self.min is None:
                self.min = self.max = x
                return True
            if x == self.min:
                return False
            # x != min, x in {0,1} → the other value
            if self.min == self.max:
                if x < self.min:
                    self.min = x
                else:
                    self.max = x
                return True
            return False  # both already present

        if self.min is None:
            self.min = self.max = x
            return True
        if x == self.min:
            return False
        if x < self.min:
            self.min, x = x, self.min  # push old min down (new in clusters)
        elif x == self.max:
            return False

        h = self.high(x)
        l = self.low(x)
        c = self._cluster(h)
        if c.min is None:
            self._summary().insert(h)
            c.min = c.max = l  # O(1) empty insert
            newly = True
        else:
            newly = c.insert(l)
        if x > self.max:
            self.max = x
        return newly

    # ── delete (precondition: x is present) ──────────────────────────────────────────────
    def delete(self, x: int) -> None:
        if self.min == self.max:
            self.min = self.max = None
            return
        if self.u == 2:
            self.min = self.max = 1 - x  # two present → leave the other
            return

        if x == self.min:
            fc = self.summary.min  # summary non-None (≥2 elements)
            x = self.index(fc, self.clusters[fc].min)
            self.min = x

        h = self.high(x)
        l = self.low(x)
        c = self.clusters[h]
        c.delete(l)
        if c.min is None:  # cluster emptied
            self.summary.delete(h)
            del self.clusters[h]
            if x == self.max:
                sm = self.summary.max
                if sm is None:
                    self.max = self.min
                else:
                    self.max = self.index(sm, self.clusters[sm].max)
        elif x == self.max:
            self.max = self.index(h, c.max)

    # ── successor / predecessor ──────────────────────────────────────────────────────────
    def successor(self, x: int) -> int | None:
        if self.u == 2:
            if x == 0 and self.max == 1:
                return 1
            return None
        if self.min is not None and x < self.min:
            return self.min
        h = self.high(x)
        l = self.low(x)
        c = self.clusters.get(h)
        max_low = c.max if c is not None else None
        if max_low is not None and l < max_low:
            return self.index(h, c.successor(l))
        sc = self.summary.successor(h) if self.summary is not None else None
        if sc is None:
            return None
        return self.index(sc, self.clusters[sc].min)

    def predecessor(self, x: int) -> int | None:
        if self.u == 2:
            if x == 1 and self.min == 0:
                return 0
            return None
        if self.max is not None and x > self.max:
            return self.max
        h = self.high(x)
        l = self.low(x)
        c = self.clusters.get(h)
        min_low = c.min if c is not None else None
        if min_low is not None and l > min_low:
            return self.index(h, c.predecessor(l))
        pc = self.summary.predecessor(h) if self.summary is not None else None
        if pc is None:
            if self.min is not None and x > self.min:
                return self.min  # min lives outside any cluster
            return None
        return self.index(pc, self.clusters[pc].max)


class VanEmdeBoas:
    """Integer ordered set with O(log log U) insert/delete/member/successor/predecessor."""

    def __init__(self, universe: int = 65536) -> None:
        if not _is_int(universe) or universe < 1:
            raise VanEmdeBoasError("universe must be a positive int")
        self._u = _round_pow2(universe)
        self._lock = threading.Lock()
        self._root = _VEBNode(self._u)
        self._size = 0

    def _check(self, x: Any) -> None:
        if not _is_int(x):
            raise VanEmdeBoasError("value must be an int")
        if not (0 <= x < self._u):
            raise VanEmdeBoasError(f"value must be in [0, {self._u})")

    # ── mutations ──────────────────────────────────────────────────────────────────────
    def insert(self, x: int) -> bool:
        """Insert ``x``; return True iff it was newly added."""
        self._check(x)
        with self._lock:
            added = self._root.insert(x)
            if added:
                self._size += 1
            return added

    def delete(self, x: int) -> bool:
        """Delete ``x``; return True iff it was present."""
        self._check(x)
        with self._lock:
            if not self._root.member(x):
                return False
            self._root.delete(x)
            self._size -= 1
            return True

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def member(self, x: int) -> bool:
        """True iff ``x`` is in the set."""
        self._check(x)
        with self._lock:
            return self._root.member(x)

    def minimum(self) -> int | None:
        """Smallest element, or None if empty."""
        with self._lock:
            return self._root.min

    def maximum(self) -> int | None:
        """Largest element, or None if empty."""
        with self._lock:
            return self._root.max

    def successor(self, x: int) -> int | None:
        """Smallest element strictly greater than ``x``, or None."""
        self._check(x)
        with self._lock:
            return self._root.successor(x)

    def predecessor(self, x: int) -> int | None:
        """Largest element strictly less than ``x``, or None."""
        self._check(x)
        with self._lock:
            return self._root.predecessor(x)

    def reset(self) -> None:
        """Empty the set."""
        with self._lock:
            self._root = _VEBNode(self._u)
            self._size = 0

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def is_empty(self) -> bool:
        with self._lock:
            return self._size == 0

    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    @property
    def universe(self) -> int:
        return self._u

    def stats(self) -> dict:
        """Summary: ``size`` / ``universe`` / ``min`` / ``max``."""
        with self._lock:
            return {
                "size": self._size,
                "universe": self._u,
                "min": self._root.min,
                "max": self._root.max,
            }
