"""Phase 156 — Sovereign B-Tree (Bayer & McCreight, 1972).

A **multiway balanced search tree** of minimum degree ``t``: every node holds between ``t−1`` and
``2t−1`` keys, every internal node with ``k`` keys has ``k+1`` children, and **all leaves sit at
the same depth**. It is the canonical database / filesystem index, giving `O(t logₜ n)` `search` /
`insert` / `delete`. Insertion splits a full child **proactively** on the way down; deletion keeps
every node at least half-full by **borrowing** from a sibling or **merging** before it descends —
a fundamentally different *shape* from every binary tree on the platform (AVL/P155, Splay/P133,
Treap, Cartesian/P145).

This is an ordered **set** (duplicate keys ignored) over any mutually-comparable keys
(ints / floats / strings). Recursion descends one root-to-leaf path whose length is the (bounded)
B-tree height `O(logₜ n)` — never degenerate, since all leaves are equidistant — so recursion is
safe. Public methods take a single lock. Pure stdlib; deterministic.
"""

from __future__ import annotations

import threading
from typing import Any


class BTreeError(Exception):
    """Raised for an invalid B-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _orderable(key: Any) -> bool:
    return isinstance(key, int | float | str) and not isinstance(key, bool)


class _BTreeNode:
    __slots__ = ("keys", "children", "leaf")

    def __init__(self, leaf: bool) -> None:
        self.keys: list = []
        self.children: list = []
        self.leaf = leaf


class BTree:
    """Multiway balanced ordered set: O(t logₜ n) search/insert/delete, all leaves at one depth."""

    def __init__(self, min_degree: int = 3) -> None:
        if not (
            isinstance(min_degree, int) and not isinstance(min_degree, bool) and min_degree >= 2
        ):
            raise BTreeError("min_degree must be an int >= 2")
        self._t = min_degree
        self._lock = threading.Lock()
        self._root = _BTreeNode(leaf=True)
        self._size = 0

    # ── search ───────────────────────────────────────────────────────────────────────────
    def _contains(self, node: _BTreeNode, key: Any) -> bool:
        i = 0
        while i < len(node.keys) and node.keys[i] < key:
            i += 1
        if i < len(node.keys) and node.keys[i] == key:
            return True
        if node.leaf:
            return False
        return self._contains(node.children[i], key)

    def contains(self, key: Any) -> bool:
        """True iff ``key`` is in the tree."""
        if not _orderable(key):
            raise BTreeError("key must be an int, float, or str")
        with self._lock:
            try:
                return self._contains(self._root, key)
            except TypeError as exc:
                raise BTreeError("keys must be mutually comparable") from exc

    # ── insert (proactive split) ─────────────────────────────────────────────────────────
    def _split_child(self, x: _BTreeNode, i: int) -> None:
        t = self._t
        y = x.children[i]  # full: 2t-1 keys
        z = _BTreeNode(leaf=y.leaf)
        mid = y.keys[t - 1]
        z.keys = y.keys[t:]
        y.keys = y.keys[: t - 1]
        if not y.leaf:
            z.children = y.children[t:]
            y.children = y.children[:t]
        x.keys.insert(i, mid)
        x.children.insert(i + 1, z)

    def _insert_nonfull(self, x: _BTreeNode, key: Any) -> None:
        if x.leaf:
            i = len(x.keys) - 1
            x.keys.append(None)
            while i >= 0 and key < x.keys[i]:
                x.keys[i + 1] = x.keys[i]
                i -= 1
            x.keys[i + 1] = key
            return
        i = len(x.keys) - 1
        while i >= 0 and key < x.keys[i]:
            i -= 1
        i += 1
        if len(x.children[i].keys) == 2 * self._t - 1:
            self._split_child(x, i)
            if key > x.keys[i]:
                i += 1
        self._insert_nonfull(x.children[i], key)

    def insert(self, key: Any) -> bool:
        """Insert ``key``; return True iff it was newly added (duplicates ignored)."""
        if not _orderable(key):
            raise BTreeError("key must be an int, float, or str")
        with self._lock:
            try:
                if self._contains(self._root, key):
                    return False
                r = self._root
                if len(r.keys) == 2 * self._t - 1:
                    s = _BTreeNode(leaf=False)
                    s.children.append(r)
                    self._root = s
                    self._split_child(s, 0)
                    self._insert_nonfull(s, key)
                else:
                    self._insert_nonfull(r, key)
            except TypeError as exc:
                raise BTreeError("keys must be mutually comparable") from exc
            self._size += 1
            return True

    # ── delete (borrow / merge) ──────────────────────────────────────────────────────────
    def _subtree_min(self, node: _BTreeNode) -> Any:
        while not node.leaf:
            node = node.children[0]
        return node.keys[0]

    def _subtree_max(self, node: _BTreeNode) -> Any:
        while not node.leaf:
            node = node.children[-1]
        return node.keys[-1]

    def _merge(self, x: _BTreeNode, i: int) -> None:
        """Merge children[i], keys[i], children[i+1] into children[i]."""
        child = x.children[i]
        sib = x.children[i + 1]
        child.keys.append(x.keys[i])
        child.keys.extend(sib.keys)
        if not child.leaf:
            child.children.extend(sib.children)
        x.keys.pop(i)
        x.children.pop(i + 1)

    def _ensure_child(self, x: _BTreeNode, i: int) -> int:
        """Guarantee x.children[i] has >= t keys (borrow / merge); return the index to descend."""
        t = self._t
        if len(x.children[i].keys) >= t:
            return i
        child = x.children[i]
        if i > 0 and len(x.children[i - 1].keys) >= t:  # borrow from left
            left = x.children[i - 1]
            child.keys.insert(0, x.keys[i - 1])
            x.keys[i - 1] = left.keys.pop()
            if not child.leaf:
                child.children.insert(0, left.children.pop())
            return i
        if i < len(x.children) - 1 and len(x.children[i + 1].keys) >= t:  # borrow from right
            right = x.children[i + 1]
            child.keys.append(x.keys[i])
            x.keys[i] = right.keys.pop(0)
            if not child.leaf:
                child.children.append(right.children.pop(0))
            return i
        if i < len(x.children) - 1:  # merge with right
            self._merge(x, i)
            return i
        self._merge(x, i - 1)  # merge with left
        return i - 1

    def _delete(self, x: _BTreeNode, key: Any) -> None:
        i = 0
        while i < len(x.keys) and x.keys[i] < key:
            i += 1
        if i < len(x.keys) and x.keys[i] == key:
            if x.leaf:
                x.keys.pop(i)
                return
            left, right = x.children[i], x.children[i + 1]
            if len(left.keys) >= self._t:
                pred = self._subtree_max(left)
                x.keys[i] = pred
                self._delete(left, pred)
            elif len(right.keys) >= self._t:
                succ = self._subtree_min(right)
                x.keys[i] = succ
                self._delete(right, succ)
            else:
                self._merge(x, i)
                self._delete(x.children[i], key)
            return
        if x.leaf:
            return  # not present (guarded by contains)
        j = self._ensure_child(x, i)
        self._delete(x.children[j], key)

    def delete(self, key: Any) -> bool:
        """Delete ``key``; return True iff it was present."""
        if not _orderable(key):
            raise BTreeError("key must be an int, float, or str")
        with self._lock:
            try:
                if not self._contains(self._root, key):
                    return False
                self._delete(self._root, key)
                if not self._root.leaf and len(self._root.keys) == 0:
                    self._root = self._root.children[0]
            except TypeError as exc:
                raise BTreeError("keys must be mutually comparable") from exc
            self._size -= 1
            return True

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def minimum(self) -> Any | None:
        """Smallest key, or None if empty."""
        with self._lock:
            if self._size == 0:
                return None
            return self._subtree_min(self._root)

    def maximum(self) -> Any | None:
        """Largest key, or None if empty."""
        with self._lock:
            if self._size == 0:
                return None
            return self._subtree_max(self._root)

    def _in_order(self, node: _BTreeNode, out: list) -> None:
        if node.leaf:
            out.extend(node.keys)
            return
        for i, k in enumerate(node.keys):
            self._in_order(node.children[i], out)
            out.append(k)
        self._in_order(node.children[-1], out)

    def in_order(self) -> list:
        """All keys in ascending order."""
        with self._lock:
            out: list = []
            self._in_order(self._root, out)
            return out

    def height(self) -> int:
        """Number of levels (0 if empty)."""
        with self._lock:
            if self._size == 0:
                return 0
            h = 1
            node = self._root
            while not node.leaf:
                h += 1
                node = node.children[0]
            return h

    def reset(self) -> None:
        """Empty the set."""
        with self._lock:
            self._root = _BTreeNode(leaf=True)
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
    def min_degree(self) -> int:
        return self._t

    def stats(self) -> dict:
        """Summary: ``size`` / ``height`` / ``min_degree`` / ``min`` / ``max``."""
        with self._lock:
            if self._size == 0:
                return {"size": 0, "height": 0, "min_degree": self._t, "min": None, "max": None}
            h = 1
            node = self._root
            while not node.leaf:
                h += 1
                node = node.children[0]
            return {
                "size": self._size,
                "height": h,
                "min_degree": self._t,
                "min": self._subtree_min(self._root),
                "max": self._subtree_max(self._root),
            }
