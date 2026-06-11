"""Phase 145 — Sovereign Cartesian Tree (Vuillemin, 1980).

A **binary tree built from a sequence** that is simultaneously a **binary-search tree on
position** and a **min-heap on value** — a new capability for the platform. It is constructed
in `O(n)` by a single left-to-right scan with a stack: each new element pops the larger-valued
nodes off the right spine, adopts the last one popped as its left child, and becomes the right
child of whatever remains on the stack. Its in-order traversal recovers the original index
order (so the values come back in their original sequence).

Its defining property is the **range-minimum ↔ lowest-common-ancestor equivalence**: the
minimum of any index range `[l, r]` is the value at the **LCA** of positions `l` and `r` in
the tree, so `range_min(l, r)` is an LCA lookup (here via parent pointers + a depth array). On
ties the leftmost occurrence wins (a strict ``>`` pop rule).

This is *different* from the doubling-table Sparse Table (P138): the same range-min query, but
via an explicit tree that also underlies treap construction and suffix-tree links. Every
operation is iterative (stack build, BFS depth, parent-walk LCA), so it is immune to recursion
limits even on a degenerate (sorted) sequence. Pure stdlib; thread-safe via a single
``threading.Lock``; deterministic (static — built once from the sequence).
"""

from __future__ import annotations

import threading
from typing import Any


class CartesianTreeError(Exception):
    """Raised for an invalid Cartesian-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class CartesianTree:
    """Min-Cartesian tree over a numeric sequence (range-min via LCA)."""

    def __init__(self, values: Any = None) -> None:
        self._lock = threading.Lock()
        self._build([] if values is None else values)

    # ── build (stack, O(n)) ──────────────────────────────────────────────────────────
    def _build_locked(self, values: Any) -> None:
        try:
            vals = list(values)
        except TypeError as exc:
            raise CartesianTreeError("values must be iterable") from exc
        for v in vals:
            if not _num(v):
                raise CartesianTreeError(f"every value must be a number, got {v!r}")

        n = len(vals)
        left = [-1] * n
        right = [-1] * n
        parent = [-1] * n
        stack: list = []
        for i in range(n):
            last = -1
            while stack and vals[stack[-1]] > vals[i]:  # strict ⇒ leftmost min on ties
                last = stack.pop()
            left[i] = last
            if last != -1:
                parent[last] = i
            if stack:
                right[stack[-1]] = i
                parent[i] = stack[-1]
            stack.append(i)
        root = stack[0] if stack else -1

        # depth array (iterative DFS from root)
        depth = [0] * n
        if root != -1:
            st = [root]
            while st:
                u = st.pop()
                for c in (left[u], right[u]):
                    if c != -1:
                        depth[c] = depth[u] + 1
                        st.append(c)

        self._vals = vals
        self._n = n
        self._left = left
        self._right = right
        self._parent = parent
        self._depth = depth
        self._root = root

    def _build(self, values: Any) -> None:
        with self._lock:
            self._build_locked(values)

    def build(self, values: Any) -> None:
        """(Re)build the tree from ``values`` (static — replaces any prior contents)."""
        with self._lock:
            self._build_locked(values)

    # ── range-min via LCA ────────────────────────────────────────────────────────────
    def _lca(self, a: int, b: int) -> int:
        parent, depth = self._parent, self._depth
        while depth[a] > depth[b]:
            a = parent[a]
        while depth[b] > depth[a]:
            b = parent[b]
        while a != b:
            a = parent[a]
            b = parent[b]
        return a

    def range_argmin(self, lo: int, hi: int) -> int:
        """Index of the minimum value in ``[lo, hi]`` (inclusive); leftmost on ties."""
        if not _is_int(lo) or not _is_int(hi):
            raise CartesianTreeError("lo and hi must be ints")
        with self._lock:
            if not (0 <= lo <= hi < self._n):
                raise CartesianTreeError(f"need 0 <= lo <= hi < {self._n}")
            return self._lca(lo, hi)

    def range_min(self, lo: int, hi: int) -> Any:
        """Minimum value in the index range ``[lo, hi]`` (inclusive)."""
        if not _is_int(lo) or not _is_int(hi):
            raise CartesianTreeError("lo and hi must be ints")
        with self._lock:
            if not (0 <= lo <= hi < self._n):
                raise CartesianTreeError(f"need 0 <= lo <= hi < {self._n}")
            return self._vals[self._lca(lo, hi)]

    # ── introspection ──────────────────────────────────────────────────────────────────
    def inorder(self) -> list:
        """Indices in in-order (a valid Cartesian tree yields ``0, 1, …, n-1``)."""
        with self._lock:
            out: list = []
            stack: list = []
            cur = self._root
            while stack or cur != -1:
                while cur != -1:
                    stack.append(cur)
                    cur = self._left[cur]
                cur = stack.pop()
                out.append(cur)
                cur = self._right[cur]
            return out

    def sequence(self) -> list:
        """The original value sequence."""
        with self._lock:
            return list(self._vals)

    def structure(self) -> dict:
        """The tree shape: ``root`` and the ``parent`` / ``left`` / ``right`` arrays (-1 = none)."""
        with self._lock:
            return {
                "root": self._root,
                "parent": list(self._parent),
                "left": list(self._left),
                "right": list(self._right),
            }

    def reset(self) -> None:
        """Empty the tree."""
        with self._lock:
            self._build_locked([])

    def __len__(self) -> int:
        return self._n

    @property
    def size(self) -> int:
        return self._n

    @property
    def root_index(self) -> int:
        return self._root

    def _height(self) -> int:
        if self._root == -1:
            return 0
        return max(self._depth) + 1

    def height(self) -> int:
        with self._lock:
            return self._height()

    def stats(self) -> dict:
        """Summary: ``size`` / ``height`` / ``root_index``."""
        with self._lock:
            return {"size": self._n, "height": self._height(), "root_index": self._root}
