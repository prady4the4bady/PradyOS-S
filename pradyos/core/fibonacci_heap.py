"""Phase 154 — Sovereign Fibonacci Heap (Fredman & Tarjan, 1984).

A **mergeable min-priority-queue** with `O(1)` amortized `insert` / `find_min` / `decrease_key`
and `O(log n)` amortized `extract_min` — the asymptotically optimal heap behind Dijkstra/Prim.
It is a forest of heap-ordered trees with a pointer to the minimum root. `extract_min`
**consolidates** roots of equal degree (linking the larger-key root under the smaller via a degree
array until all root degrees are distinct); `decrease_key` **cuts** a node to the root list when it
violates heap order and performs **cascading cuts** up through already-marked ancestors.

This is a *different mechanism* from the two-pass Pairing Heap/P150, the meld-only Skew Heap/P136,
and the double-ended Min-Max Heap/P144. Nodes are objects in circular doubly-linked sibling lists;
a stable integer **handle** returned by ``insert`` (mapped to its node) makes ``decrease_key``
addressable. Consolidate and cascading-cut are both **iterative** (no recursion). Pure stdlib;
thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

from typing import Any, Optional

import threading


class FibonacciHeapError(Exception):
    """Raised for an invalid Fibonacci-heap operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class _FibNode:
    __slots__ = ("key", "handle", "parent", "child", "left", "right", "degree", "mark", "alive")

    def __init__(self, key: float, handle: int) -> None:
        self.key = key
        self.handle = handle
        self.parent: Optional[_FibNode] = None
        self.child: Optional[_FibNode] = None
        self.left: _FibNode = self
        self.right: _FibNode = self
        self.degree = 0
        self.mark = False
        self.alive = True


class FibonacciHeap:
    """Mergeable min-PQ; O(1) amortized insert/decrease_key, O(log n) extract_min."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._min: Optional[_FibNode] = None
        self._size = 0
        self._handles: dict[int, _FibNode] = {}
        self._next = 0

    # ── root-list helpers ────────────────────────────────────────────────────────────────
    def _add_to_root(self, node: _FibNode) -> None:
        if self._min is None:
            node.left = node.right = node
            self._min = node
        else:
            node.right = self._min.right
            node.left = self._min
            self._min.right.left = node
            self._min.right = node

    @staticmethod
    def _iter_circular(start: Optional[_FibNode]) -> list:
        if start is None:
            return []
        out = []
        cur = start
        while True:
            out.append(cur)
            cur = cur.right
            if cur is start:
                break
        return out

    # ── insert ───────────────────────────────────────────────────────────────────────────
    def insert(self, value: float) -> int:
        """Insert ``value``; return a stable handle for later ``decrease_key``."""
        if not _is_num(value):
            raise FibonacciHeapError("value must be a number")
        with self._lock:
            h = self._next
            self._next += 1
            node = _FibNode(value, h)
            self._handles[h] = node
            self._add_to_root(node)
            if value < self._min.key:
                self._min = node
            self._size += 1
            return h

    # ── find_min ─────────────────────────────────────────────────────────────────────────
    def find_min(self) -> float:
        """Smallest value (raises if empty)."""
        with self._lock:
            if self._min is None:
                raise FibonacciHeapError("heap is empty")
            return self._min.key

    def find_min_handle(self) -> int:
        with self._lock:
            if self._min is None:
                raise FibonacciHeapError("heap is empty")
            return self._min.handle

    # ── link / consolidate ───────────────────────────────────────────────────────────────
    def _link(self, y: _FibNode, x: _FibNode) -> None:
        """Make root ``y`` a child of root ``x`` (precondition: x.key <= y.key)."""
        y.left.right = y.right
        y.right.left = y.left
        y.parent = x
        if x.child is None:
            x.child = y
            y.left = y.right = y
        else:
            y.right = x.child.right
            y.left = x.child
            x.child.right.left = y
            x.child.right = y
        x.degree += 1
        y.mark = False

    def _consolidate(self) -> None:
        degree_table: dict[int, _FibNode] = {}
        for w in self._iter_circular(self._min):
            x = w
            d = x.degree
            while d in degree_table:
                y = degree_table.pop(d)
                if y.key < x.key:
                    x, y = y, x
                self._link(y, x)
                d += 1
            degree_table[d] = x
        # rebuild the root list and the min pointer from the surviving roots
        self._min = None
        for node in degree_table.values():
            node.left = node.right = node
            node.parent = None
            self._add_to_root(node)
        if self._min is not None:
            best = self._min
            for node in self._iter_circular(self._min):
                if node.key < best.key:
                    best = node
            self._min = best

    # ── extract_min ──────────────────────────────────────────────────────────────────────
    def extract_min(self) -> float:
        """Remove and return the smallest value (raises if empty)."""
        with self._lock:
            z = self._min
            if z is None:
                raise FibonacciHeapError("heap is empty")
            # move z's children to the root list
            for c in self._iter_circular(z.child):
                c.parent = None
                c.left = c.right = c
                self._add_to_root(c)
            z.child = None
            # remove z from the root list
            nxt = z.right
            z.left.right = z.right
            z.right.left = z.left
            if z is nxt:
                self._min = None
            else:
                self._min = nxt
                self._consolidate()
            self._size -= 1
            z.alive = False
            del self._handles[z.handle]
            return z.key

    # ── decrease_key ───────────────────────────────────────────────────────────────────────
    def _cut(self, x: _FibNode, y: _FibNode) -> None:
        """Cut ``x`` from its parent ``y`` and move it to the root list."""
        if x.right is x:
            y.child = None
        else:
            x.left.right = x.right
            x.right.left = x.left
            if y.child is x:
                y.child = x.right
        y.degree -= 1
        x.parent = None
        x.mark = False
        x.left = self._min.left
        x.right = self._min
        self._min.left.right = x
        self._min.left = x

    def _cascading_cut(self, y: _FibNode) -> None:
        while True:
            z = y.parent
            if z is None:
                break
            if not y.mark:
                y.mark = True
                break
            self._cut(y, z)
            y = z

    def decrease_key(self, handle: int, value: float) -> None:
        """Lower the value at ``handle`` to ``value`` (must not increase it)."""
        if not _is_int(handle):
            raise FibonacciHeapError("handle must be an int")
        if not _is_num(value):
            raise FibonacciHeapError("value must be a number")
        with self._lock:
            node = self._handles.get(handle)
            if node is None or not node.alive:
                raise FibonacciHeapError("handle is not a live element")
            if value > node.key:
                raise FibonacciHeapError("decrease_key cannot increase the value")
            node.key = value
            y = node.parent
            if y is not None and node.key < y.key:
                self._cut(node, y)
                self._cascading_cut(y)
            if node.key < self._min.key:
                self._min = node

    # ── maintenance / introspection ──────────────────────────────────────────────────────
    def reset(self) -> None:
        """Discard all elements."""
        with self._lock:
            self._min = None
            self._size = 0
            self._handles = {}
            self._next = 0

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
            num_trees = len(self._iter_circular(self._min))
            return {"size": self._size, "num_trees": num_trees,
                    "min": None if self._min is None else self._min.key}
