"""Phase 149 — Sovereign Persistent Segment Tree (fully-persistent, versioned range-sum).

A **fully-persistent range-sum index**: the array starts as *version 0*, and every point
``update`` produces a **new version** in `O(log n)` while leaving all earlier versions intact and
queryable forever. Persistence is achieved by **path-copying** — an update copies only the
`O(log n)` nodes on the root→leaf path and *shares* every untouched subtree with the previous
version — so `k` updates over an `n`-element array use only `O(k log n)` extra nodes.

This is the platform's *first* persistent / immutable data structure, distinct from every
*ephemeral* range index (Fenwick/P80, Segment Tree/P81, Sparse Table/P138, 2D Fenwick/P146, Sqrt
Decomposition/P147) and the Li Chao line-container/P148: those keep a single mutable state, this
keeps the entire history.

Nodes live in parallel arrays (``_sum`` / ``_left`` / ``_right``) indexed by an integer node-id;
a node is never mutated after creation (append-only), which is what makes old versions safe. A
balanced tree over ``[0, n)`` is built once for version 0; each subsequent root is the head of a
new path that re-uses the old structure. ``build`` / ``update`` / ``range_sum`` / ``point_query``
are all iterative. Pure stdlib; thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

import threading
from typing import Any


class PersistentSegmentTreeError(Exception):
    """Raised for an invalid persistent-segment-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class PersistentSegmentTree:
    """Versioned range-sum: each point update yields a new, independently-queryable version."""

    def __init__(self, values: Any = None) -> None:
        self._lock = threading.Lock()
        self._clear()
        if values is not None:
            self.build(values)

    # ── internal node store (append-only; never mutate an existing node) ─────────────────
    def _clear(self) -> None:
        self._sum: list[float] = []
        self._left: list[int] = []
        self._right: list[int] = []
        self._versions: list[int] = []  # version index -> root node-id
        self._n = 0

    def _new_node(self, s: float, lc: int, rc: int) -> int:
        self._sum.append(s)
        self._left.append(lc)
        self._right.append(rc)
        return len(self._sum) - 1

    # ── build version 0 (iterative post-order) ───────────────────────────────────────────
    def build(self, values: Any) -> None:
        """(Re)build from ``values`` as version 0; discards any prior history."""
        try:
            arr = list(values)
        except TypeError as exc:
            raise PersistentSegmentTreeError("values must be iterable") from exc
        if not arr:
            raise PersistentSegmentTreeError("values must be non-empty")
        for v in arr:
            if not _is_num(v):
                raise PersistentSegmentTreeError(f"every value must be a number, got {v!r}")
        with self._lock:
            self._clear()
            self._n = len(arr)
            root = self._build_iter(arr)
            self._versions.append(root)

    def _build_iter(self, arr: list) -> int:
        # explicit-stack post-order: frame = [l, r, state, left_id, right_id]
        n = self._n
        ret = -1
        stack = [[0, n - 1, 0, -1, -1]]
        while stack:
            frame = stack[-1]
            l, r, state = frame[0], frame[1], frame[2]
            if l == r:
                ret = self._new_node(arr[l], -1, -1)
                stack.pop()
                continue
            mid = (l + r) // 2
            if state == 0:
                frame[2] = 1
                stack.append([l, mid, 0, -1, -1])
            elif state == 1:
                frame[3] = ret  # left child id (just completed)
                frame[2] = 2
                stack.append([mid + 1, r, 0, -1, -1])
            else:
                frame[4] = ret  # right child id (just completed)
                ret = self._new_node(self._sum[frame[3]] + self._sum[frame[4]], frame[3], frame[4])
                stack.pop()
        return ret

    # ── update → new version (iterative path-copy) ───────────────────────────────────────
    def update(self, version: int, i: int, value: float) -> int:
        """Set index ``i`` to ``value`` in ``version``; return the new version index."""
        if not _is_int(version) or not _is_int(i):
            raise PersistentSegmentTreeError("version and i must be ints")
        if not _is_num(value):
            raise PersistentSegmentTreeError("value must be a number")
        with self._lock:
            if not (0 <= version < len(self._versions)):
                raise PersistentSegmentTreeError(
                    f"version must be in [0, {len(self._versions) - 1}]"
                )
            if not (0 <= i < self._n):
                raise PersistentSegmentTreeError(f"i must be in [0, {self._n - 1}]")
            cur = self._versions[version]
            l, r = 0, self._n - 1
            path = []  # (old_node_id, dir) from root down to the leaf
            while l != r:
                mid = (l + r) // 2
                if i <= mid:
                    path.append((cur, 0))
                    cur = self._left[cur]
                    r = mid
                else:
                    path.append((cur, 1))
                    cur = self._right[cur]
                    l = mid + 1
            child = self._new_node(value, -1, -1)  # new leaf
            for old_id, d in reversed(path):  # rebuild path bottom-up, sharing siblings
                if d == 0:
                    lc, rc = child, self._right[old_id]
                else:
                    lc, rc = self._left[old_id], child
                child = self._new_node(self._sum[lc] + self._sum[rc], lc, rc)
            self._versions.append(child)
            return len(self._versions) - 1

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def range_sum(self, version: int, lo: int, hi: int) -> float:
        """Sum of ``[lo, hi]`` (inclusive) in ``version``."""
        if not _is_int(version) or not _is_int(lo) or not _is_int(hi):
            raise PersistentSegmentTreeError("version, lo and hi must be ints")
        with self._lock:
            if not (0 <= version < len(self._versions)):
                raise PersistentSegmentTreeError(
                    f"version must be in [0, {len(self._versions) - 1}]"
                )
            if not (0 <= lo <= hi < self._n):
                raise PersistentSegmentTreeError(f"need 0 <= lo <= hi < {self._n}")
            total = 0
            stack = [(self._versions[version], 0, self._n - 1)]
            while stack:
                nid, l, r = stack.pop()
                if hi < l or r < lo:
                    continue
                if lo <= l and r <= hi:
                    total += self._sum[nid]
                    continue
                mid = (l + r) // 2
                stack.append((self._left[nid], l, mid))
                stack.append((self._right[nid], mid + 1, r))
            return total

    def point_query(self, version: int, i: int) -> float:
        """Value at index ``i`` in ``version``."""
        if not _is_int(version) or not _is_int(i):
            raise PersistentSegmentTreeError("version and i must be ints")
        with self._lock:
            if not (0 <= version < len(self._versions)):
                raise PersistentSegmentTreeError(
                    f"version must be in [0, {len(self._versions) - 1}]"
                )
            if not (0 <= i < self._n):
                raise PersistentSegmentTreeError(f"i must be in [0, {self._n - 1}]")
            cur = self._versions[version]
            l, r = 0, self._n - 1
            while l != r:
                mid = (l + r) // 2
                if i <= mid:
                    cur = self._left[cur]
                    r = mid
                else:
                    cur = self._right[cur]
                    l = mid + 1
            return self._sum[cur]

    def reset(self) -> None:
        """Discard all versions and contents."""
        with self._lock:
            self._clear()

    # ── introspection ──────────────────────────────────────────────────────────────────────
    @property
    def size(self) -> int:
        return self._n

    @property
    def num_versions(self) -> int:
        return len(self._versions)

    def __len__(self) -> int:
        return len(self._versions)

    def stats(self) -> dict:
        """Summary: ``size`` / ``num_versions`` / ``nodes``."""
        with self._lock:
            return {"size": self._n, "num_versions": len(self._versions), "nodes": len(self._sum)}
