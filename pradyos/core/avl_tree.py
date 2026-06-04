"""Phase 155 — Sovereign AVL Tree (Adelson-Velsky & Landis, 1962).

A **height-balanced comparison-ordered set** with *guaranteed* `O(log n)` `insert` / `delete` /
`contains` / `successor` / `predecessor` / `min` / `max`. Every node tracks its subtree height;
after each update the tree rebalances with single/double rotations whenever a node's balance factor
(`height(left) − height(right)`) leaves `{−1, 0, +1}`, so the height stays `≤ 1.44 log₂(n+2)`.

Unlike the platform's other search trees this one is *strictly* balanced on every update — distinct
from the amortized Splay Tree/P133, the randomized Treap, the RMQ Cartesian Tree/P145, and the
integer-universe vEB/P152 (AVL orders *any* mutually-comparable keys: ints, floats, strings). A
classic ordered-set: duplicates are ignored, `successor`/`predecessor` work for keys not present.

The recursion descends one root-to-leaf path whose length is the (bounded) AVL height, so depth is
structurally `≤ 1.44 log₂ n` — never degenerate — and recursion is safe. Public methods take a
single lock; the recursive helpers are lock-free. Pure stdlib; deterministic.
"""

from __future__ import annotations

from typing import Any, Optional

import threading


class AVLTreeError(Exception):
    """Raised for an invalid AVL-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _orderable(key: Any) -> bool:
    return isinstance(key, (int, float, str)) and not isinstance(key, bool)


class _AVLNode:
    __slots__ = ("key", "left", "right", "height")

    def __init__(self, key: Any) -> None:
        self.key = key
        self.left: Optional[_AVLNode] = None
        self.right: Optional[_AVLNode] = None
        self.height = 1


def _h(node: Optional[_AVLNode]) -> int:
    return node.height if node is not None else 0


def _bf(node: _AVLNode) -> int:
    return _h(node.left) - _h(node.right)


def _update(node: _AVLNode) -> None:
    node.height = 1 + max(_h(node.left), _h(node.right))


def _rotate_right(y: _AVLNode) -> _AVLNode:
    x = y.left
    y.left = x.right
    x.right = y
    _update(y)
    _update(x)
    return x


def _rotate_left(x: _AVLNode) -> _AVLNode:
    y = x.right
    x.right = y.left
    y.left = x
    _update(x)
    _update(y)
    return y


def _rebalance(node: _AVLNode) -> _AVLNode:
    _update(node)
    bf = _bf(node)
    if bf > 1:                                  # left-heavy
        if _bf(node.left) < 0:                  # left-right
            node.left = _rotate_left(node.left)
        return _rotate_right(node)
    if bf < -1:                                 # right-heavy
        if _bf(node.right) > 0:                 # right-left
            node.right = _rotate_right(node.right)
        return _rotate_left(node)
    return node


class AVLTree:
    """Height-balanced ordered set: guaranteed O(log n) insert/delete/search/successor."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._root: Optional[_AVLNode] = None
        self._size = 0

    # ── insert ───────────────────────────────────────────────────────────────────────────
    def _insert(self, node: Optional[_AVLNode], key: Any) -> tuple:
        if node is None:
            return _AVLNode(key), True
        if key == node.key:
            return node, False
        if key < node.key:
            node.left, added = self._insert(node.left, key)
        else:
            node.right, added = self._insert(node.right, key)
        if added:
            node = _rebalance(node)
        return node, added

    def insert(self, key: Any) -> bool:
        """Insert ``key``; return True iff it was newly added (duplicates ignored)."""
        if not _orderable(key):
            raise AVLTreeError("key must be an int, float, or str")
        with self._lock:
            try:
                self._root, added = self._insert(self._root, key)
            except TypeError as exc:
                raise AVLTreeError("keys must be mutually comparable") from exc
            if added:
                self._size += 1
            return added

    # ── delete ───────────────────────────────────────────────────────────────────────────
    def _min_node(self, node: _AVLNode) -> _AVLNode:
        while node.left is not None:
            node = node.left
        return node

    def _delete(self, node: Optional[_AVLNode], key: Any) -> tuple:
        if node is None:
            return None, False
        if key < node.key:
            node.left, removed = self._delete(node.left, key)
        elif key > node.key:
            node.right, removed = self._delete(node.right, key)
        else:
            removed = True
            if node.left is None:
                return node.right, True
            if node.right is None:
                return node.left, True
            succ = self._min_node(node.right)
            node.key = succ.key
            node.right, _ = self._delete(node.right, succ.key)
        if removed:
            node = _rebalance(node)
        return node, removed

    def delete(self, key: Any) -> bool:
        """Delete ``key``; return True iff it was present."""
        if not _orderable(key):
            raise AVLTreeError("key must be an int, float, or str")
        with self._lock:
            try:
                self._root, removed = self._delete(self._root, key)
            except TypeError as exc:
                raise AVLTreeError("keys must be mutually comparable") from exc
            if removed:
                self._size -= 1
            return removed

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def contains(self, key: Any) -> bool:
        """True iff ``key`` is in the set."""
        if not _orderable(key):
            raise AVLTreeError("key must be an int, float, or str")
        with self._lock:
            node = self._root
            try:
                while node is not None:
                    if key == node.key:
                        return True
                    node = node.left if key < node.key else node.right
            except TypeError as exc:
                raise AVLTreeError("keys must be mutually comparable") from exc
            return False

    def successor(self, key: Any) -> Optional[Any]:
        """Smallest key strictly greater than ``key`` (key need not be present), or None."""
        if not _orderable(key):
            raise AVLTreeError("key must be an int, float, or str")
        with self._lock:
            node = self._root
            succ = None
            try:
                while node is not None:
                    if node.key > key:
                        succ = node.key
                        node = node.left
                    else:
                        node = node.right
            except TypeError as exc:
                raise AVLTreeError("keys must be mutually comparable") from exc
            return succ

    def predecessor(self, key: Any) -> Optional[Any]:
        """Largest key strictly less than ``key`` (key need not be present), or None."""
        if not _orderable(key):
            raise AVLTreeError("key must be an int, float, or str")
        with self._lock:
            node = self._root
            pred = None
            try:
                while node is not None:
                    if node.key < key:
                        pred = node.key
                        node = node.right
                    else:
                        node = node.left
            except TypeError as exc:
                raise AVLTreeError("keys must be mutually comparable") from exc
            return pred

    def minimum(self) -> Optional[Any]:
        """Smallest key, or None if empty."""
        with self._lock:
            if self._root is None:
                return None
            return self._min_node(self._root).key

    def maximum(self) -> Optional[Any]:
        """Largest key, or None if empty."""
        with self._lock:
            node = self._root
            if node is None:
                return None
            while node.right is not None:
                node = node.right
            return node.key

    def in_order(self) -> list:
        """All keys in ascending order (iterative traversal)."""
        with self._lock:
            out = []
            stack = []
            node = self._root
            while stack or node is not None:
                while node is not None:
                    stack.append(node)
                    node = node.left
                node = stack.pop()
                out.append(node.key)
                node = node.right
            return out

    def height(self) -> int:
        """Height of the tree (0 if empty)."""
        with self._lock:
            return _h(self._root)

    def reset(self) -> None:
        """Empty the set."""
        with self._lock:
            self._root = None
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

    def stats(self) -> dict:
        """Summary: ``size`` / ``height`` / ``min`` / ``max``."""
        with self._lock:
            mn = None if self._root is None else self._min_node(self._root).key
            mx = None
            if self._root is not None:
                node = self._root
                while node.right is not None:
                    node = node.right
                mx = node.key
            return {"size": self._size, "height": _h(self._root), "min": mn, "max": mx}
