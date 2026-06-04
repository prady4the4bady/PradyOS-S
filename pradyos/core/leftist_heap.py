"""Phase 158 — Sovereign Leftist Heap (Crane, 1972).

A **mergeable min-priority-queue with a *worst-case* `O(log n)` `meld`** (hence `insert` and
`extract_min`). Every node keeps the **rank** (null-path-length) of its subtree and maintains the
*leftist invariant* `rank(left) ≥ rank(right)`, which forces the **right spine to have length
`≤ log₂(n+1)`**. Merging two heaps walks only their right spines — at each step the smaller root
adopts the merge of its right child with the other heap, then swaps children if needed to restore
the invariant — so the work is bounded by the right-spine lengths.

This is a *different guarantee* from the platform's other heaps: the Skew Heap/P136 melds in
*amortized* `O(log n)` with no balance field, while the Pairing/P150 and Fibonacci/P154 heaps
target `O(1)`-amortized `decrease_key`; the Min-Max Heap/P144 is an array double-ended queue. A
leftist heap is a min-PQ that also supports an explicit **`merge(other)`** of two instances.

The merge recursion descends only the right spines, so its depth is structurally bounded at
`O(log n)` by the leftist invariant — never input-dependent. Pure stdlib; thread-safe via a single
``threading.Lock`` (two-instance ``merge`` acquires both locks in ``id()`` order); deterministic.
"""

from __future__ import annotations

from typing import Any, Optional

import threading


class LeftistHeapError(Exception):
    """Raised for an invalid leftist-heap operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class _LHNode:
    __slots__ = ("key", "left", "right", "rank")

    def __init__(self, key: float) -> None:
        self.key = key
        self.left: Optional[_LHNode] = None
        self.right: Optional[_LHNode] = None
        self.rank = 1                       # rank(leaf) = 1; rank(None) = 0


def _rank(node: Optional[_LHNode]) -> int:
    return node.rank if node is not None else 0


class LeftistHeap:
    """Mergeable min-PQ with worst-case O(log n) meld via the null-path-length (leftist) invariant."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._root: Optional[_LHNode] = None
        self._size = 0

    # ── merge (descends the right spines; bounded by O(log n)) ───────────────────────────
    def _merge(self, a: Optional[_LHNode], b: Optional[_LHNode]) -> Optional[_LHNode]:
        if a is None:
            return b
        if b is None:
            return a
        if a.key > b.key:
            a, b = b, a                     # a is the smaller root
        a.right = self._merge(a.right, b)
        if _rank(a.left) < _rank(a.right):
            a.left, a.right = a.right, a.left
        a.rank = _rank(a.right) + 1
        return a

    # ── insert ───────────────────────────────────────────────────────────────────────────
    def insert(self, value: float) -> None:
        """Insert ``value`` (duplicates allowed)."""
        if not _is_num(value):
            raise LeftistHeapError("value must be a number")
        with self._lock:
            self._root = self._merge(self._root, _LHNode(value))
            self._size += 1

    # ── find_min / extract_min ───────────────────────────────────────────────────────────
    def find_min(self) -> float:
        """Smallest value (raises if empty)."""
        with self._lock:
            if self._root is None:
                raise LeftistHeapError("heap is empty")
            return self._root.key

    def extract_min(self) -> float:
        """Remove and return the smallest value (raises if empty)."""
        with self._lock:
            if self._root is None:
                raise LeftistHeapError("heap is empty")
            root = self._root
            self._root = self._merge(root.left, root.right)
            self._size -= 1
            return root.key

    # ── merge two instances (id()-ordered locking) ───────────────────────────────────────
    def merge(self, other: "LeftistHeap") -> None:
        """Meld all elements of ``other`` into this heap; ``other`` is left empty."""
        if not isinstance(other, LeftistHeap):
            raise LeftistHeapError("can only merge with another LeftistHeap")
        if other is self:
            raise LeftistHeapError("cannot merge a heap with itself")
        first, second = (self, other) if id(self) < id(other) else (other, self)
        with first._lock:
            with second._lock:
                self._root = self._merge(self._root, other._root)
                self._size += other._size
                other._root = None
                other._size = 0

    # ── maintenance / introspection ──────────────────────────────────────────────────────
    def reset(self) -> None:
        """Discard all elements."""
        with self._lock:
            self._root = None
            self._size = 0

    def is_empty(self) -> bool:
        with self._lock:
            return self._size == 0

    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    def stats(self) -> dict:
        """Summary: ``size`` / ``rank`` (right-spine length) / ``min`` (None if empty)."""
        with self._lock:
            return {"size": self._size, "rank": _rank(self._root),
                    "min": None if self._root is None else self._root.key}
