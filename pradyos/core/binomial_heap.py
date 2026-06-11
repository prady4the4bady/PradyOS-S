"""Phase 160 — Sovereign Binomial Heap (Vuillemin, 1978).

A **mergeable min-priority-queue** structured as a forest of **binomial trees**: a `Bₖ` tree has
exactly `2ᵏ` nodes and is formed by linking two `Bₖ₋₁` trees, and the heap keeps at most one tree
of each order in a root list sorted by increasing degree. Its hallmark is that `merge` is exactly
**binary addition** — equal-order trees are linked with a "carry" — giving `O(log n)` `merge`,
`insert`, `extract_min`, and `decrease_key`.

This completes the platform's mergeable-heap family alongside the *amortized*-meld Skew Heap/P136
and the *worst-case*-meld Leftist Heap/P158; binomial is the structure the Fibonacci Heap/P154
lazily improves upon. Stable integer **handles** returned by ``insert`` (drawn from a process-wide
counter so two heaps never collide, which keeps cross-instance ``merge`` valid) make
``decrease_key`` addressable — `decrease_key` bubbles the element up its tree by exchanging the
(key, handle) payload with ancestors and keeping the handle map in sync.

The root list has `O(log n)` trees and each binomial tree has depth `O(log n)`, so every walk is
structurally bounded — there is no recursion. Pure stdlib; thread-safe via a single
``threading.Lock`` (two-instance ``merge`` acquires both in ``id()`` order); deterministic.
"""

from __future__ import annotations

import itertools
import threading
from typing import Any

_HANDLES = itertools.count()  # process-wide unique handle ids (next() is atomic under the GIL)


class BinomialHeapError(Exception):
    """Raised for an invalid binomial-heap operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class _BinNode:
    __slots__ = ("key", "handle", "parent", "child", "sibling", "degree")

    def __init__(self, key: float, handle: int) -> None:
        self.key = key
        self.handle = handle
        self.parent: _BinNode | None = None
        self.child: _BinNode | None = None
        self.sibling: _BinNode | None = None
        self.degree = 0


class BinomialHeap:
    """Mergeable min-PQ: forest of binomial trees, O(log n) insert/extract_min/decrease_key/merge."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._head: _BinNode | None = None
        self._size = 0
        self._handles: dict[int, _BinNode] = {}

    # ── structural helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _merge_roots(a: _BinNode | None, b: _BinNode | None) -> _BinNode | None:
        """Merge two root lists into one sorted by increasing degree (no linking yet)."""
        if a is None:
            return b
        if b is None:
            return a
        if a.degree <= b.degree:
            head = a
            a = a.sibling
        else:
            head = b
            b = b.sibling
        tail = head
        while a is not None and b is not None:
            if a.degree <= b.degree:
                tail.sibling = a
                a = a.sibling
            else:
                tail.sibling = b
                b = b.sibling
            tail = tail.sibling
        tail.sibling = a if a is not None else b
        return head

    @staticmethod
    def _link(y: _BinNode, z: _BinNode) -> None:
        """Make ``y`` (larger key) a child of ``z`` (smaller key)."""
        y.parent = z
        y.sibling = z.child
        z.child = y
        z.degree += 1

    def _union(self, a: _BinNode | None, b: _BinNode | None) -> _BinNode | None:
        head = self._merge_roots(a, b)
        if head is None:
            return None
        prev: _BinNode | None = None
        curr: _BinNode = head
        nxt = curr.sibling
        while nxt is not None:
            if curr.degree != nxt.degree or (
                nxt.sibling is not None and nxt.sibling.degree == curr.degree
            ):
                prev = curr
                curr = nxt
            elif curr.key <= nxt.key:
                curr.sibling = nxt.sibling
                self._link(nxt, curr)
            else:
                if prev is None:
                    head = nxt
                else:
                    prev.sibling = nxt
                self._link(curr, nxt)
                curr = nxt
            nxt = curr.sibling
        return head

    def _min_root(self) -> _BinNode:
        best = self._head
        node = self._head.sibling
        while node is not None:
            if node.key < best.key:
                best = node
            node = node.sibling
        return best

    # ── insert ───────────────────────────────────────────────────────────────────────────
    def insert(self, value: float) -> int:
        """Insert ``value``; return a stable handle for later ``decrease_key``."""
        if not _is_num(value):
            raise BinomialHeapError("value must be a number")
        with self._lock:
            h = next(_HANDLES)
            node = _BinNode(value, h)
            self._handles[h] = node
            self._head = self._union(self._head, node)
            self._size += 1
            return h

    # ── find_min ─────────────────────────────────────────────────────────────────────────
    def find_min(self) -> float:
        """Smallest value (raises if empty)."""
        with self._lock:
            if self._head is None:
                raise BinomialHeapError("heap is empty")
            return self._min_root().key

    def find_min_handle(self) -> int:
        with self._lock:
            if self._head is None:
                raise BinomialHeapError("heap is empty")
            return self._min_root().handle

    # ── extract_min ──────────────────────────────────────────────────────────────────────
    def extract_min(self) -> float:
        """Remove and return the smallest value (raises if empty)."""
        with self._lock:
            if self._head is None:
                raise BinomialHeapError("heap is empty")
            # locate the min root and its predecessor in the root list
            minr = self._head
            minprev: _BinNode | None = None
            prev: _BinNode | None = None
            node = self._head
            while node is not None:
                if node.key < minr.key:
                    minr = node
                    minprev = prev
                prev = node
                node = node.sibling
            # remove minr from the root list
            if minprev is None:
                self._head = minr.sibling
            else:
                minprev.sibling = minr.sibling
            # reverse minr's children into their own root list
            child = minr.child
            newh: _BinNode | None = None
            while child is not None:
                nxt = child.sibling
                child.sibling = newh
                child.parent = None
                newh = child
                child = nxt
            self._head = self._union(self._head, newh)
            self._size -= 1
            del self._handles[minr.handle]
            return minr.key

    # ── decrease_key ───────────────────────────────────────────────────────────────────────
    def decrease_key(self, handle: int, value: float) -> None:
        """Lower the value at ``handle`` to ``value`` (must not increase it)."""
        if not _is_int(handle):
            raise BinomialHeapError("handle must be an int")
        if not _is_num(value):
            raise BinomialHeapError("value must be a number")
        with self._lock:
            node = self._handles.get(handle)
            if node is None:
                raise BinomialHeapError("handle is not a live element")
            if value > node.key:
                raise BinomialHeapError("decrease_key cannot increase the value")
            node.key = value
            cur = node
            parent = cur.parent
            while parent is not None and cur.key < parent.key:
                # exchange the (key, handle) payload up, keeping the handle map in sync
                cur.key, parent.key = parent.key, cur.key
                cur.handle, parent.handle = parent.handle, cur.handle
                self._handles[cur.handle] = cur
                self._handles[parent.handle] = parent
                cur = parent
                parent = cur.parent

    # ── merge two instances (id()-ordered locking) ───────────────────────────────────────
    def merge(self, other: BinomialHeap) -> None:
        """Meld all elements of ``other`` into this heap; ``other`` is left empty."""
        if not isinstance(other, BinomialHeap):
            raise BinomialHeapError("can only merge with another BinomialHeap")
        if other is self:
            raise BinomialHeapError("cannot merge a heap with itself")
        first, second = (self, other) if id(self) < id(other) else (other, self)
        with first._lock:
            with second._lock:
                self._head = self._union(self._head, other._head)
                self._handles.update(other._handles)  # handles are process-unique → no clash
                self._size += other._size
                other._head = None
                other._handles = {}
                other._size = 0

    # ── maintenance / introspection ──────────────────────────────────────────────────────
    def reset(self) -> None:
        """Discard all elements."""
        with self._lock:
            self._head = None
            self._size = 0
            self._handles = {}

    def is_empty(self) -> bool:
        with self._lock:
            return self._size == 0

    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    def stats(self) -> dict:
        """Summary: ``size`` / ``num_trees`` / ``min`` (None if empty)."""
        with self._lock:
            num_trees = 0
            node = self._head
            while node is not None:
                num_trees += 1
                node = node.sibling
            return {
                "size": self._size,
                "num_trees": num_trees,
                "min": None if self._head is None else self._min_root().key,
            }
