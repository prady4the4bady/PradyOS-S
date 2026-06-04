"""Phase 166 — Sovereign Sparse Segment Tree (dynamic segment tree).

A segment tree over a **huge coordinate space** ``[0, U)`` (e.g. ``U = 10**18``) whose nodes are
**created lazily** along the root→leaf path of each update. ``q`` updates therefore use only
``O(q log U)`` memory instead of the ``O(U)`` an array would need — so it answers `O(log U)`
**point-add** / **point-assign** and **range-sum** with *no coordinate compression*, the capability
the dense Segment Tree/P81 and Lazy Segment Tree/P163 cannot offer.

Each update walks down allocating any missing children; each query prunes whole *absent* subtrees
(a missing node contributes 0). The recursion descends one root→leaf path whose length is
``⌈log₂ U⌉`` — at most ~62 for a `2^62` universe — so it is **structurally bounded** (never
input-dependent). Pure stdlib; thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

from typing import Any, Optional

import threading


class SparseSegmentTreeError(Exception):
    """Raised for an invalid sparse-segment-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class _Node:
    __slots__ = ("sum", "lc", "rc")

    def __init__(self) -> None:
        self.sum: float = 0
        self.lc: Optional[_Node] = None
        self.rc: Optional[_Node] = None


class SparseSegmentTree:
    """Dynamic segment tree over [0, U): lazy nodes, O(log U) point-update + range-sum."""

    def __init__(self, universe: int = 1 << 62) -> None:
        if not _is_int(universe) or universe < 1:
            raise SparseSegmentTreeError("universe must be a positive int")
        self._u = universe
        self._lock = threading.Lock()
        self._root: Optional[_Node] = None
        self._node_count = 0

    # ── update (point add) ─────────────────────────────────────────────────────────────────
    def _add(self, node: Optional[_Node], lo: int, hi: int, idx: int, delta: float) -> _Node:
        if node is None:
            node = _Node()
            self._node_count += 1
        node.sum += delta
        if lo == hi:
            return node
        mid = (lo + hi) // 2
        if idx <= mid:
            node.lc = self._add(node.lc, lo, mid, idx, delta)
        else:
            node.rc = self._add(node.rc, mid + 1, hi, idx, delta)
        return node

    def update(self, index: int, delta: float) -> None:
        """Add ``delta`` to the value at ``index``."""
        if not _is_int(index):
            raise SparseSegmentTreeError("index must be an int")
        if not _is_num(delta):
            raise SparseSegmentTreeError("delta must be a number")
        with self._lock:
            if not (0 <= index < self._u):
                raise SparseSegmentTreeError(f"index must be in [0, {self._u})")
            self._root = self._add(self._root, 0, self._u - 1, index, delta)

    def point_assign(self, index: int, value: float) -> None:
        """Set the value at ``index`` to ``value`` (absolute)."""
        if not _is_int(index):
            raise SparseSegmentTreeError("index must be an int")
        if not _is_num(value):
            raise SparseSegmentTreeError("value must be a number")
        with self._lock:
            if not (0 <= index < self._u):
                raise SparseSegmentTreeError(f"index must be in [0, {self._u})")
            cur = self._point(self._root, 0, self._u - 1, index)
            self._root = self._add(self._root, 0, self._u - 1, index, value - cur)

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def _range(self, node: Optional[_Node], lo: int, hi: int, ql: int, qr: int) -> float:
        if node is None or qr < lo or hi < ql:
            return 0
        if ql <= lo and hi <= qr:
            return node.sum
        mid = (lo + hi) // 2
        return (self._range(node.lc, lo, mid, ql, qr)
                + self._range(node.rc, mid + 1, hi, ql, qr))

    def _point(self, node: Optional[_Node], lo: int, hi: int, idx: int) -> float:
        while node is not None and lo != hi:
            mid = (lo + hi) // 2
            if idx <= mid:
                node = node.lc
                hi = mid
            else:
                node = node.rc
                lo = mid + 1
        return node.sum if node is not None else 0

    def range_sum(self, lo: int, hi: int) -> float:
        """Sum of values over ``[lo, hi]`` (inclusive)."""
        if not _is_int(lo) or not _is_int(hi):
            raise SparseSegmentTreeError("lo and hi must be ints")
        with self._lock:
            if not (0 <= lo <= hi < self._u):
                raise SparseSegmentTreeError(f"need 0 <= lo <= hi < {self._u}")
            return self._range(self._root, 0, self._u - 1, lo, hi)

    def point_query(self, index: int) -> float:
        """Value at ``index``."""
        if not _is_int(index):
            raise SparseSegmentTreeError("index must be an int")
        with self._lock:
            if not (0 <= index < self._u):
                raise SparseSegmentTreeError(f"index must be in [0, {self._u})")
            return self._point(self._root, 0, self._u - 1, index)

    def reset(self) -> None:
        """Discard all entries."""
        with self._lock:
            self._root = None
            self._node_count = 0

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def is_empty(self) -> bool:
        with self._lock:
            return self._root is None

    @property
    def universe(self) -> int:
        return self._u

    @property
    def num_nodes(self) -> int:
        return self._node_count

    def total(self) -> float:
        """Sum over the whole universe."""
        with self._lock:
            return self._root.sum if self._root is not None else 0

    def stats(self) -> dict:
        """Summary: ``universe`` / ``num_nodes`` / ``total``."""
        with self._lock:
            return {"universe": self._u, "num_nodes": self._node_count,
                    "total": self._root.sum if self._root is not None else 0}
