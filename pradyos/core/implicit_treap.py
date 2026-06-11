"""Phase 162 — Sovereign Implicit Treap (rope / indexable sequence).

The platform's first **sequence** structure: a randomized balanced binary tree that represents a
*list* keyed **implicitly by position** — a node's index is the size of its left subtree, so there
is no stored key. Built on the treap `split` / `merge` primitives, it supports `O(log n)`:

* `insert(index, value)` — splice a value in at any position,
* `delete(index)` — remove the value at a position,
* `get(index)` / `set(index, value)` — random access,
* `range_sum(lo, hi)` — sum of a contiguous slice (each node caches its subtree sum).

Unlike every ordered set / heap shipped so far this represents a *list* whose middle can be spliced
in `O(log n)` (an array needs `O(n)`), and unlike the key-ordered Treap it orders by position.

Node priorities come from a **seeded** RNG, so the structure is fully deterministic, and because
priorities are internal the tree height stays `O(log n)` with high probability *regardless of the
operation sequence* — no input can force it deep. The `split`/`merge` recursion descends one
root-to-leaf path (that `O(log n)` height). Pure stdlib; thread-safe via a single ``threading.Lock``.
"""

from __future__ import annotations

import random
import threading
from typing import Any


class ImplicitTreapError(Exception):
    """Raised for an invalid implicit-treap operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


class _ITNode:
    __slots__ = ("value", "priority", "size", "sum", "left", "right")

    def __init__(self, value: float, priority: int) -> None:
        self.value = value
        self.priority = priority
        self.size = 1
        self.sum = value
        self.left: _ITNode | None = None
        self.right: _ITNode | None = None


def _size(node: _ITNode | None) -> int:
    return node.size if node is not None else 0


def _sum(node: _ITNode | None) -> float:
    return node.sum if node is not None else 0


def _update(node: _ITNode) -> None:
    node.size = 1 + _size(node.left) + _size(node.right)
    node.sum = node.value + _sum(node.left) + _sum(node.right)


class ImplicitTreap:
    """Indexable sequence: O(log n) insert-at / delete-at / get / set / range-sum via split+merge."""

    def __init__(self, seed: int = 0) -> None:
        if not _is_int(seed):
            raise ImplicitTreapError("seed must be an int")
        self._lock = threading.Lock()
        self._root: _ITNode | None = None
        self._rng = random.Random(seed)

    # ── split / merge primitives ──────────────────────────────────────────────────────────
    def _split(self, node: _ITNode | None, k: int) -> tuple:
        """Split ``node`` so the left result holds the first ``k`` elements."""
        if node is None:
            return None, None
        ls = _size(node.left)
        if k <= ls:
            left, node.left = self._split(node.left, k)
            _update(node)
            return left, node
        node.right, right = self._split(node.right, k - ls - 1)
        _update(node)
        return node, right

    def _merge(self, a: _ITNode | None, b: _ITNode | None) -> _ITNode | None:
        """Merge two treaps where every element of ``a`` precedes every element of ``b``."""
        if a is None:
            return b
        if b is None:
            return a
        if a.priority > b.priority:
            a.right = self._merge(a.right, b)
            _update(a)
            return a
        b.left = self._merge(a, b.left)
        _update(b)
        return b

    # ── insert / delete ───────────────────────────────────────────────────────────────────
    def insert(self, index: int, value: float) -> None:
        """Insert ``value`` so it ends up at position ``index`` (``0 <= index <= size``)."""
        if not _is_int(index):
            raise ImplicitTreapError("index must be an int")
        if not _is_num(value):
            raise ImplicitTreapError("value must be a number")
        with self._lock:
            n = _size(self._root)
            if not (0 <= index <= n):
                raise ImplicitTreapError(f"index must be in [0, {n}]")
            node = _ITNode(value, self._rng.getrandbits(31))
            left, right = self._split(self._root, index)
            self._root = self._merge(self._merge(left, node), right)

    def delete(self, index: int) -> float:
        """Delete and return the value at position ``index`` (``0 <= index < size``)."""
        if not _is_int(index):
            raise ImplicitTreapError("index must be an int")
        with self._lock:
            n = _size(self._root)
            if not (0 <= index < n):
                raise ImplicitTreapError(f"index must be in [0, {n - 1}]")
            left, rest = self._split(self._root, index)
            mid, right = self._split(rest, 1)
            self._root = self._merge(left, right)
            return mid.value

    # ── random access ─────────────────────────────────────────────────────────────────────
    def get(self, index: int) -> float:
        """Value at position ``index``."""
        if not _is_int(index):
            raise ImplicitTreapError("index must be an int")
        with self._lock:
            if not (0 <= index < _size(self._root)):
                raise ImplicitTreapError(f"index must be in [0, {_size(self._root) - 1}]")
            node = self._root
            i = index
            while True:
                ls = _size(node.left)
                if i < ls:
                    node = node.left
                elif i == ls:
                    return node.value
                else:
                    i -= ls + 1
                    node = node.right

    def set(self, index: int, value: float) -> None:
        """Set the value at position ``index``."""
        if not _is_int(index):
            raise ImplicitTreapError("index must be an int")
        if not _is_num(value):
            raise ImplicitTreapError("value must be a number")
        with self._lock:
            if not (0 <= index < _size(self._root)):
                raise ImplicitTreapError(f"index must be in [0, {_size(self._root) - 1}]")
            path = []
            node = self._root
            i = index
            while True:
                ls = _size(node.left)
                if i < ls:
                    path.append(node)
                    node = node.left
                elif i == ls:
                    break
                else:
                    i -= ls + 1
                    path.append(node)
                    node = node.right
            node.value = value
            _update(node)
            for anc in reversed(path):
                _update(anc)

    # ── range sum ──────────────────────────────────────────────────────────────────────────
    def range_sum(self, lo: int, hi: int) -> float:
        """Sum of values at positions ``[lo, hi]`` (inclusive)."""
        if not _is_int(lo) or not _is_int(hi):
            raise ImplicitTreapError("lo and hi must be ints")
        with self._lock:
            n = _size(self._root)
            if not (0 <= lo <= hi < n):
                raise ImplicitTreapError(f"need 0 <= lo <= hi < {n}")
            left, rest = self._split(self._root, lo)
            mid, right = self._split(rest, hi - lo + 1)
            total = _sum(mid)
            self._root = self._merge(self._merge(left, mid), right)
            return total

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def to_list(self) -> list:
        """All values in order (iterative in-order traversal)."""
        with self._lock:
            out = []
            stack = []
            node = self._root
            while stack or node is not None:
                while node is not None:
                    stack.append(node)
                    node = node.left
                node = stack.pop()
                out.append(node.value)
                node = node.right
            return out

    def reset(self) -> None:
        """Empty the sequence."""
        with self._lock:
            self._root = None

    def is_empty(self) -> bool:
        with self._lock:
            return self._root is None

    def __len__(self) -> int:
        return _size(self._root)

    @property
    def size(self) -> int:
        return _size(self._root)

    def stats(self) -> dict:
        """Summary: ``size`` / ``total`` (sum of all values)."""
        with self._lock:
            return {"size": _size(self._root), "total": _sum(self._root)}
