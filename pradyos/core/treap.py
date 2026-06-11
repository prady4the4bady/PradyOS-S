"""Phase 113 — Sovereign Treap (Seidel & Aragon, 1996 — *Randomized search trees*).

A **randomized balanced binary search tree**. Each node carries a ``key`` and a
``value``, plus a **random priority**; the tree is simultaneously a **binary search
tree** on keys (left < node < right) and a **max-heap** on priorities (a parent's
priority is ≥ both children's). Given any fixed key set, the heap constraint forces
a *unique* tree shape — the one a plain BST would take if the keys were inserted in
decreasing-priority order. Because the priorities are drawn at random, that order is
a uniformly random permutation, so the tree behaves like a BST built from random
insertions: its **expected height is ``≈ 2·ln n``** and ``search`` / ``insert`` /
``delete`` / ``rank`` / ``select`` all run in **O(log n) expected** time — with no
balance-factor or colour bookkeeping, just rotations.

``insert`` does an ordinary BST insert then rotates the new node up while its
priority exceeds its parent's (restoring the heap order); ``delete`` removes a node
by **merging its two subtrees** (the higher-priority child becomes the new local
root, recursively). Every node also stores its **subtree size**, which makes the
order-statistics queries ``rank(key)`` (how many keys are strictly smaller) and
``select(i)`` (the ``i``-th smallest key) run in ``O(log n)``.

This is a *different* probabilistic ordered structure from the Skip List (P78), which
randomises tower *levels* over a linked list; the treap randomises node *priorities*
over a rotated tree. Priorities come from a seeded ``random.Random`` so a fixed seed
and insertion sequence reproduce the tree exactly. Pure stdlib; thread-safe via a
single ``threading.Lock`` (the public surface acquires it; the recursive helpers are
pure and never re-acquire it).
"""

from __future__ import annotations

import random
import threading
from typing import Any


class TreapError(Exception):
    """Raised for an invalid Treap operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class _Node:
    __slots__ = ("key", "value", "priority", "left", "right", "size")

    def __init__(self, key: Any, value: Any, priority: float) -> None:
        self.key = key
        self.value = value
        self.priority = priority
        self.left: _Node | None = None
        self.right: _Node | None = None
        self.size = 1


def _size(node: _Node | None) -> int:
    return node.size if node is not None else 0


def _update(node: _Node) -> None:
    node.size = 1 + _size(node.left) + _size(node.right)


class Treap:
    """Randomized balanced BST with O(log n) expected ops and order statistics."""

    def __init__(self, seed: int = 0) -> None:
        if not _is_int(seed):
            raise TreapError(seed)
        self._seed = seed
        self._lock = threading.Lock()
        self._root: _Node | None = None
        self._rng = random.Random(seed)

    # ── rotations (pure; maintain subtree sizes) ──────────────────────────────────────
    @staticmethod
    def _rotate_right(node: _Node) -> _Node:
        pivot = node.left
        assert pivot is not None
        node.left = pivot.right
        pivot.right = node
        _update(node)
        _update(pivot)
        return pivot

    @staticmethod
    def _rotate_left(node: _Node) -> _Node:
        pivot = node.right
        assert pivot is not None
        node.right = pivot.left
        pivot.left = node
        _update(node)
        _update(pivot)
        return pivot

    # ── insert ──────────────────────────────────────────────────────────────────────
    def _insert(self, node: _Node | None, key: Any, value: Any, priority: float) -> _Node:
        if node is None:
            return _Node(key, value, priority)
        if key == node.key:
            node.value = value  # update in place; no duplicate
            return node
        if key < node.key:
            node.left = self._insert(node.left, key, value, priority)
            if node.left.priority > node.priority:
                node = self._rotate_right(node)
        else:
            node.right = self._insert(node.right, key, value, priority)
            if node.right.priority > node.priority:
                node = self._rotate_left(node)
        _update(node)
        return node

    def insert(self, key: Any, value: Any = None) -> None:
        """Insert ``key`` (with optional ``value``), or update the value if present."""
        with self._lock:
            self._root = self._insert(self._root, key, value, self._rng.random())

    # ── delete (merge the two subtrees of the removed node) ───────────────────────────
    def _merge(self, left: _Node | None, right: _Node | None) -> _Node | None:
        if left is None:
            return right
        if right is None:
            return left
        if left.priority > right.priority:
            left.right = self._merge(left.right, right)
            _update(left)
            return left
        right.left = self._merge(left, right.left)
        _update(right)
        return right

    def _delete(self, node: _Node | None, key: Any) -> _Node | None:
        if node is None:
            return None
        if key == node.key:
            return self._merge(node.left, node.right)
        if key < node.key:
            node.left = self._delete(node.left, key)
        else:
            node.right = self._delete(node.right, key)
        _update(node)
        return node

    def delete(self, key: Any) -> bool:
        """Remove ``key``; return True if it was present."""
        with self._lock:
            before = _size(self._root)
            self._root = self._delete(self._root, key)
            return _size(self._root) < before

    # ── queries ─────────────────────────────────────────────────────────────────────
    def _find(self, key: Any) -> _Node | None:
        node = self._root
        while node is not None:
            if key == node.key:
                return node
            node = node.left if key < node.key else node.right
        return node

    def contains(self, key: Any) -> bool:
        with self._lock:
            return self._find(key) is not None

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    def get(self, key: Any, default: Any = None) -> Any:
        """Return the value stored for ``key``, or ``default`` if absent."""
        with self._lock:
            node = self._find(key)
            return node.value if node is not None else default

    def search(self, key: Any) -> Any:
        """Return the value for ``key``; raise :class:`TreapError` if absent."""
        with self._lock:
            node = self._find(key)
            if node is None:
                raise TreapError(f"key not found: {key!r}")
            return node.value

    def rank(self, key: Any) -> int:
        """Number of stored keys strictly less than ``key`` (its 0-based position)."""
        with self._lock:
            r = 0
            node = self._root
            while node is not None:
                if key > node.key:
                    r += _size(node.left) + 1
                    node = node.right
                else:
                    node = node.left
            return r

    def select(self, index: int) -> Any:
        """Return the ``index``-th smallest key (0-based); raise if out of range."""
        with self._lock:
            if not _is_int(index) or index < 0 or index >= _size(self._root):
                raise TreapError(index)
            node = self._root
            i = index
            while node is not None:
                left_size = _size(node.left)
                if i < left_size:
                    node = node.left
                elif i == left_size:
                    return node.key
                else:
                    i -= left_size + 1
                    node = node.right
            raise TreapError(index)  # unreachable given the bounds check

    def min_key(self) -> Any:
        with self._lock:
            if self._root is None:
                raise TreapError("empty treap")
            node = self._root
            while node.left is not None:
                node = node.left
            return node.key

    def max_key(self) -> Any:
        with self._lock:
            if self._root is None:
                raise TreapError("empty treap")
            node = self._root
            while node.right is not None:
                node = node.right
            return node.key

    def keys(self) -> list:
        """All keys in ascending order (in-order traversal)."""
        with self._lock:
            out: list = []
            self._inorder(self._root, out)
            return out

    def _inorder(self, node: _Node | None, out: list) -> None:
        # Iterative to avoid deep recursion on a pathological tree.
        stack: list[_Node] = []
        cur = node
        while cur is not None or stack:
            while cur is not None:
                stack.append(cur)
                cur = cur.left
            cur = stack.pop()
            out.append(cur.key)
            cur = cur.right

    def _height(self, node: _Node | None) -> int:
        if node is None:
            return 0
        return 1 + max(self._height(node.left), self._height(node.right))

    def height(self) -> int:
        with self._lock:
            return self._height(self._root)

    def reset(self, seed: int | None = None) -> None:
        """Empty the tree; optionally reconfigure ``seed`` (re-seeds the priority RNG)."""
        with self._lock:
            if seed is not None:
                if not _is_int(seed):
                    raise TreapError(seed)
                self._seed = seed
            self._root = None
            self._rng = random.Random(self._seed)

    def __len__(self) -> int:
        with self._lock:
            return _size(self._root)

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``size`` / ``height`` / ``min`` / ``max`` (None if empty) / ``seed``."""
        with self._lock:
            size = _size(self._root)
            mn = mx = None
            if self._root is not None:
                node = self._root
                while node.left is not None:
                    node = node.left
                mn = node.key
                node = self._root
                while node.right is not None:
                    node = node.right
                mx = node.key
            return {
                "size": size,
                "height": self._height(self._root),
                "min": mn,
                "max": mx,
                "seed": self._seed,
            }
