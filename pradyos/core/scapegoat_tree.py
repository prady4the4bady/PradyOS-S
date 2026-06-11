"""Phase 159 — Sovereign Scapegoat Tree (Galperin & Rivest, 1993).

A **self-balancing BST that stores no per-node balance field and performs no rotations**. It lets
the tree drift on insertion and, whenever a freshly inserted node lands deeper than
`log_{1/α}(n)`, walks back up to the **scapegoat** — the highest ancestor that is *not*
weight-`α`-balanced (one child holds more than `α` of the subtree) — and **rebuilds that whole
subtree perfectly balanced** in linear time. Deletions simply unlink the node; once the live count
drops below `α · (high-water size)`, the *entire* tree is rebuilt. These two amortized rebuilds
keep the height at `≤ log_{1/α}(n)`, giving amortized `O(log n)` `insert` / `delete` and worst-case
`O(log n)` `contains`.

This is a balancing *paradigm* the platform lacks — amortized rebuild, distinct from the
rotation-balanced AVL/P155, the split/merge B-Tree/P156, the randomized Treap, and the
move-to-root Splay Tree/P133. It is an ordered set over any mutually-comparable keys (duplicates
ignored). Subtree sizes are computed on demand (no augmentation), so a rebuild costs `O(subtree)`,
amortized `O(log n)` per update. Pure stdlib; thread-safe via a single ``threading.Lock``;
deterministic.
"""

from __future__ import annotations

import math
import threading
from typing import Any


class ScapegoatTreeError(Exception):
    """Raised for an invalid scapegoat-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _orderable(key: Any) -> bool:
    return isinstance(key, int | float | str) and not isinstance(key, bool)


class _SGNode:
    __slots__ = ("key", "left", "right")

    def __init__(self, key: Any) -> None:
        self.key = key
        self.left: _SGNode | None = None
        self.right: _SGNode | None = None


class ScapegoatTree:
    """Rebuild-balanced ordered set: amortized O(log n) insert/delete, no rotations / balance field."""

    def __init__(self, alpha: float = 2 / 3) -> None:
        if not (isinstance(alpha, float) and 0.5 < alpha < 1.0):
            raise ScapegoatTreeError("alpha must be a float in (0.5, 1.0)")
        self._alpha = alpha
        self._lock = threading.Lock()
        self._root: _SGNode | None = None
        self._n = 0
        self._max_n = 0

    # ── helpers (under the lock) ─────────────────────────────────────────────────────────
    def _size(self, node: _SGNode | None) -> int:
        total = 0
        stack = [node]
        while stack:
            nd = stack.pop()
            if nd is not None:
                total += 1
                stack.append(nd.left)
                stack.append(nd.right)
        return total

    def _flatten(self, node: _SGNode | None) -> list:
        out = []
        stack = []
        cur = node
        while stack or cur is not None:
            while cur is not None:
                stack.append(cur)
                cur = cur.left
            cur = stack.pop()
            out.append(cur)
            cur = cur.right
        return out  # in-order list of nodes

    def _build_balanced(self, nodes: list) -> _SGNode | None:
        if not nodes:
            return None
        mid = len(nodes) // 2
        root = nodes[mid]
        root.left = self._build_balanced(nodes[:mid])
        root.right = self._build_balanced(nodes[mid + 1 :])
        return root

    def _rebuild(self, node: _SGNode) -> _SGNode:
        return self._build_balanced(self._flatten(node))

    def _height_bound(self, n: int) -> float:
        if n <= 1:
            return 0.0
        return math.floor(math.log(n) / math.log(1.0 / self._alpha))

    # ── insert ───────────────────────────────────────────────────────────────────────────
    def insert(self, key: Any) -> bool:
        """Insert ``key``; return True iff newly added (duplicates ignored)."""
        if not _orderable(key):
            raise ScapegoatTreeError("key must be an int, float, or str")
        with self._lock:
            try:
                return self._insert_locked(key)
            except TypeError as exc:
                raise ScapegoatTreeError("keys must be mutually comparable") from exc

    def _insert_locked(self, key: Any) -> bool:
        if self._root is None:
            self._root = _SGNode(key)
            self._n = 1
            self._max_n = max(self._max_n, 1)
            return True
        path = []
        node = self._root
        while node is not None:
            path.append(node)
            if key == node.key:
                return False
            node = node.left if key < node.key else node.right
        parent = path[-1]
        new_node = _SGNode(key)
        if key < parent.key:
            parent.left = new_node
        else:
            parent.right = new_node
        self._n += 1
        self._max_n = max(self._max_n, self._n)
        # depth of the new node == len(path); rebalance if it exceeds the height bound
        if len(path) > self._height_bound(self._n):
            self._rebalance_after_insert(path, new_node)
        return True

    def _rebalance_after_insert(self, path: list, new_node: _SGNode) -> None:
        # walk up from the new node to find the scapegoat
        child = new_node
        child_size = 1
        for i in range(len(path) - 1, -1, -1):
            parent = path[i]
            sibling = parent.right if parent.left is child else parent.left
            parent_size = child_size + self._size(sibling) + 1
            if child_size > self._alpha * parent_size:
                rebuilt = self._rebuild(parent)
                if i == 0:
                    self._root = rebuilt
                else:
                    grand = path[i - 1]
                    if grand.left is parent:
                        grand.left = rebuilt
                    else:
                        grand.right = rebuilt
                return
            child = parent
            child_size = parent_size

    # ── delete ───────────────────────────────────────────────────────────────────────────
    def delete(self, key: Any) -> bool:
        """Delete ``key``; return True iff it was present."""
        if not _orderable(key):
            raise ScapegoatTreeError("key must be an int, float, or str")
        with self._lock:
            try:
                return self._delete_locked(key)
            except TypeError as exc:
                raise ScapegoatTreeError("keys must be mutually comparable") from exc

    def _delete_locked(self, key: Any) -> bool:
        parent = None
        node = self._root
        while node is not None and node.key != key:
            parent = node
            node = node.left if key < node.key else node.right
        if node is None:
            return False
        # node has two children: copy successor key, then delete successor (≤1 child)
        if node.left is not None and node.right is not None:
            parent = node
            succ = node.right
            while succ.left is not None:
                parent = succ
                succ = succ.left
            node.key = succ.key
            node = succ
        child = node.left if node.left is not None else node.right  # ≤1 child
        if parent is None:
            self._root = child
        elif parent.left is node:
            parent.left = child
        else:
            parent.right = child
        self._n -= 1
        # rebuild the whole tree when it has shrunk enough
        if self._n <= self._alpha * self._max_n:
            self._root = self._rebuild(self._root) if self._root is not None else None
            self._max_n = self._n
        return True

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def contains(self, key: Any) -> bool:
        """True iff ``key`` is in the set."""
        if not _orderable(key):
            raise ScapegoatTreeError("key must be an int, float, or str")
        with self._lock:
            node = self._root
            try:
                while node is not None:
                    if key == node.key:
                        return True
                    node = node.left if key < node.key else node.right
            except TypeError as exc:
                raise ScapegoatTreeError("keys must be mutually comparable") from exc
            return False

    def minimum(self) -> Any | None:
        """Smallest key, or None if empty."""
        with self._lock:
            if self._root is None:
                return None
            node = self._root
            while node.left is not None:
                node = node.left
            return node.key

    def maximum(self) -> Any | None:
        """Largest key, or None if empty."""
        with self._lock:
            if self._root is None:
                return None
            node = self._root
            while node.right is not None:
                node = node.right
            return node.key

    def in_order(self) -> list:
        """All keys in ascending order."""
        with self._lock:
            return [nd.key for nd in self._flatten(self._root)]

    def height(self) -> int:
        """Height of the tree in nodes (0 if empty)."""
        with self._lock:
            return self._height_of(self._root)

    def _height_of(self, root: _SGNode | None) -> int:
        if root is None:
            return 0
        best = 0
        stack = [(root, 1)]
        while stack:
            nd, d = stack.pop()
            if d > best:
                best = d
            if nd.left is not None:
                stack.append((nd.left, d + 1))
            if nd.right is not None:
                stack.append((nd.right, d + 1))
        return best

    def reset(self) -> None:
        """Empty the set."""
        with self._lock:
            self._root = None
            self._n = 0
            self._max_n = 0

    # ── introspection ──────────────────────────────────────────────────────────────────────
    def is_empty(self) -> bool:
        with self._lock:
            return self._n == 0

    def __len__(self) -> int:
        return self._n

    @property
    def size(self) -> int:
        return self._n

    @property
    def alpha(self) -> float:
        return self._alpha

    def stats(self) -> dict:
        """Summary: ``size`` / ``height`` / ``alpha`` / ``min`` / ``max``."""
        with self._lock:
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
                "size": self._n,
                "height": self._height_of(self._root),
                "alpha": self._alpha,
                "min": mn,
                "max": mx,
            }
