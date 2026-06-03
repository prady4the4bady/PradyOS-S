"""Phase 133 — Sovereign Splay Tree (Sleator & Tarjan, 1985).

A **self-adjusting binary search tree** — a new ordered-map mechanism for the platform.
Unlike the *randomised* balance of Treap/P113 or the *probabilistic levels* of Skip List/P78,
a splay tree stores **no balance metadata**. Instead every access **splays** the touched node
to the root through a sequence of rotations (`zig`, `zig-zig`, `zig-zag`), so recently and
frequently accessed keys migrate near the root: repeated-access and sequential workloads beat
the `O(log n)` worst case, and the tree is *statically / dynamically optimal* up to a constant.

This implementation uses the classic **top-down splay** (Sleator–Tarjan): a single descent
assembles a left tree (keys known to be `< target`) and a right tree (keys `> target`) and
re-roots at the closest key. Every public operation that touches a node re-roots it:

  * ``insert`` / ``find`` / ``contains`` splay the (searched) key to the root;
  * ``delete`` splays the key out, then joins the two subtrees by splaying the predecessor up;
  * ``min`` / ``max`` / ``predecessor`` / ``successor`` splay the resulting neighbour up.

Lookups are *amortised* `O(log n)` and the structure is **deterministic** — it carries no
randomness, so the tree shape is a pure function of the operation sequence. In-order traversal
yields keys in sorted order (it is a BST). Pure stdlib; thread-safe via a single
``threading.Lock`` (a read still mutates structure, so every op holds the lock).
"""

from __future__ import annotations

import threading
from typing import Any

_MISSING = object()


class SplayTreeError(Exception):
    """Raised for an invalid Splay-tree operation. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class _Node:
    __slots__ = ("key", "value", "left", "right")

    def __init__(self, key: Any, value: Any) -> None:
        self.key = key
        self.value = value
        self.left: "_Node | None" = None
        self.right: "_Node | None" = None


def _key_kind(key: Any) -> str:
    if isinstance(key, bool):
        raise SplayTreeError("key must be int, float or str (not bool)")
    if isinstance(key, (int, float)):
        return "num"
    if isinstance(key, str):
        return "str"
    raise SplayTreeError("key must be int, float or str")


class SplayTree:
    """Self-adjusting BST (top-down splay); an exact ordered key→value map."""

    def __init__(self) -> None:
        self._root: _Node | None = None
        self._size = 0
        self._kind: str | None = None          # 'num' or 'str' — keys must be mutually orderable
        self._lock = threading.Lock()

    # ── splay (top-down Sleator–Tarjan) ──────────────────────────────────────────────
    @staticmethod
    def _splay(root: _Node, key: Any) -> _Node:
        """Re-root the subtree at the node closest to ``key`` and return the new root."""
        header = _Node(None, None)             # header.right → left tree, header.left → right tree
        left_max = header                      # current attach point of the left tree (its max)
        right_min = header                     # current attach point of the right tree (its min)
        t = root
        while True:
            if key < t.key:
                if t.left is None:
                    break
                if key < t.left.key:           # zig-zig → rotate right
                    y = t.left
                    t.left = y.right
                    y.right = t
                    t = y
                    if t.left is None:
                        break
                right_min.left = t             # link right
                right_min = t
                t = t.left
            elif key > t.key:
                if t.right is None:
                    break
                if key > t.right.key:          # zig-zig → rotate left
                    y = t.right
                    t.right = y.left
                    y.left = t
                    t = y
                    if t.right is None:
                        break
                left_max.right = t             # link left
                left_max = t
                t = t.right
            else:
                break
        # assemble: t is the new root
        left_max.right = t.left
        right_min.left = t.right
        t.left = header.right
        t.right = header.left
        return t

    # ── mutation ────────────────────────────────────────────────────────────────────
    def insert(self, key: Any, value: Any = None) -> None:
        """Insert ``key → value`` (updates in place if present); splays ``key`` to the root."""
        kind = _key_kind(key)
        with self._lock:
            if self._root is None:
                self._root = _Node(key, value)
                self._kind = kind
                self._size = 1
                return
            if kind != self._kind:
                raise SplayTreeError(f"key kind {kind!r} does not match tree kind {self._kind!r}")
            self._root = self._splay(self._root, key)
            if self._root.key == key:
                self._root.value = value       # update — no size change
                return
            node = _Node(key, value)
            if key < self._root.key:
                node.left = self._root.left
                node.right = self._root
                self._root.left = None
            else:
                node.right = self._root.right
                node.left = self._root
                self._root.right = None
            self._root = node
            self._size += 1

    def delete(self, key: Any) -> bool:
        """Remove ``key``; returns whether it was present. Splays around the removal site."""
        kind = _key_kind(key)                  # validates type (raises); no shared state
        with self._lock:
            if self._root is None or kind != self._kind:
                return False
            self._root = self._splay(self._root, key)
            if self._root.key != key:
                return False
            left, right = self._root.left, self._root.right
            if left is None:
                self._root = right
            else:
                left = self._splay(left, key)  # key > every node in left → brings its max up
                left.right = right
                self._root = left
            self._size -= 1
            return True

    # ── lookup (each splays) ──────────────────────────────────────────────────────────
    def find(self, key: Any, default: Any = None) -> Any:
        """Return the value for ``key`` (splaying it to the root), or ``default`` if absent."""
        kind = _key_kind(key)                  # validates type (raises); no shared state
        with self._lock:
            if self._root is None or kind != self._kind:
                return default
            self._root = self._splay(self._root, key)
            if self._root.key == key:
                return self._root.value
            return default

    def contains(self, key: Any) -> bool:
        return self.find(key, _MISSING) is not _MISSING

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    def min(self) -> Any:
        """Smallest key (splayed to the root); raises if the tree is empty."""
        with self._lock:
            if self._root is None:
                raise SplayTreeError("min() on an empty tree")
            node = self._root
            while node.left is not None:
                node = node.left
            self._root = self._splay(self._root, node.key)
            return self._root.key

    def max(self) -> Any:
        """Largest key (splayed to the root); raises if the tree is empty."""
        with self._lock:
            if self._root is None:
                raise SplayTreeError("max() on an empty tree")
            node = self._root
            while node.right is not None:
                node = node.right
            self._root = self._splay(self._root, node.key)
            return self._root.key

    def predecessor(self, key: Any) -> Any:
        """Largest key strictly less than ``key`` (splayed up), or ``None``."""
        kind = _key_kind(key)                  # validates type (raises); no shared state
        with self._lock:
            if self._root is None or kind != self._kind:
                return None
            node, pred = self._root, None
            while node is not None:
                if node.key < key:
                    pred = node.key
                    node = node.right
                else:
                    node = node.left
            if pred is not None:
                self._root = self._splay(self._root, pred)
            return pred

    def successor(self, key: Any) -> Any:
        """Smallest key strictly greater than ``key`` (splayed up), or ``None``."""
        kind = _key_kind(key)                  # validates type (raises); no shared state
        with self._lock:
            if self._root is None or kind != self._kind:
                return None
            node, succ = self._root, None
            while node is not None:
                if node.key > key:
                    succ = node.key
                    node = node.left
                else:
                    node = node.right
            if succ is not None:
                self._root = self._splay(self._root, succ)
            return succ

    def reset(self) -> None:
        """Empty the tree."""
        with self._lock:
            self._root = None
            self._size = 0
            self._kind = None

    # ── introspection (read-only; no splay) ───────────────────────────────────────────
    def keys(self) -> list:
        """All keys in sorted (in-order) order."""
        with self._lock:
            out: list = []
            stack: list = []
            node = self._root
            while stack or node is not None:
                while node is not None:
                    stack.append(node)
                    node = node.left
                node = stack.pop()
                out.append(node.key)
                node = node.right
            return out

    def _height(self) -> int:
        if self._root is None:
            return 0
        h = 0
        stack = [(self._root, 1)]
        while stack:
            node, d = stack.pop()
            if d > h:
                h = d
            if node.left is not None:
                stack.append((node.left, d + 1))
            if node.right is not None:
                stack.append((node.right, d + 1))
        return h

    def height(self) -> int:
        with self._lock:
            return self._height()

    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    @property
    def root_key(self) -> Any:
        return self._root.key if self._root is not None else None

    @property
    def key_kind(self) -> str | None:
        return self._kind

    def stats(self) -> dict:
        """Summary: ``size`` / ``height`` / ``root_key`` / ``key_kind``."""
        with self._lock:
            return {
                "size": self._size,
                "height": self._height(),
                "root_key": self._root.key if self._root is not None else None,
                "key_kind": self._kind,
            }
