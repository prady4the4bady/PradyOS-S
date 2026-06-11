"""Phase 136 — Sovereign Skew Heap (Sleator & Tarjan, 1986).

A **self-adjusting meldable priority queue** — a new capability for the platform (there is no
heap / priority queue yet) and a thematic companion to the Splay Tree of P133: both are
self-adjusting and carry *no* balance or rank metadata.

The single primitive is **meld** (merge two heaps). Recursively it is: take the smaller of the
two roots as the new root, meld its right subtree with the other heap, then **swap that root's
children** — the child-swap is exactly what amortises the right-spine length to `O(log n)`
with no bookkeeping. Everything else is meld:

  * ``insert(v)`` melds in a singleton;
  * ``extract_min()`` removes the root and melds its two children;
  * ``meld(other)`` unions two heaps wholesale — the operation an array binary-heap can't do.

This implementation melds **iteratively**: it merges the two heaps' (already-ascending) right
spines into one sorted list, detaching right children, then relinks from the back swapping
children at each node — heap-order-preserving, and immune to Python recursion limits on
adversarial (e.g. sorted) inputs. Pure stdlib; thread-safe via a single ``threading.Lock``;
deterministic (no randomness).
"""

from __future__ import annotations

import threading
from typing import Any


class SkewHeapError(Exception):
    """Raised for an invalid Skew-heap operation. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class _Node:
    __slots__ = ("key", "left", "right")

    def __init__(self, key: Any) -> None:
        self.key = key
        self.left: _Node | None = None
        self.right: _Node | None = None


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        raise SkewHeapError("value must be int, float or str (not bool)")
    if isinstance(value, int | float):
        return "num"
    if isinstance(value, str):
        return "str"
    raise SkewHeapError("value must be int, float or str")


class SkewHeap:
    """Self-adjusting meldable min-priority-queue (iterative skew meld)."""

    def __init__(self) -> None:
        self._root: _Node | None = None
        self._size = 0
        self._kind: str | None = None  # 'num' or 'str' — values must be mutually orderable
        self._lock = threading.Lock()

    # ── meld (iterative; heap-order preserving) ───────────────────────────────────────
    @staticmethod
    def _meld(a: _Node | None, b: _Node | None) -> _Node | None:
        if a is None:
            return b
        if b is None:
            return a
        # Merge the two ascending right-spines into one sorted list, detaching right links.
        merged: list = []
        while a is not None and b is not None:
            if a.key <= b.key:
                node, a = a, a.right
            else:
                node, b = b, b.right
            node.right = None
            merged.append(node)
        tail = a if a is not None else b
        while tail is not None:
            node, tail = tail, tail.right
            node.right = None
            merged.append(node)
        # Relink from the back: each node's new left is the merged-rest, new right is its
        # original left child (heap-order holds: both children have keys ≥ the node's).
        for i in range(len(merged) - 1, 0, -1):
            parent = merged[i - 1]
            parent.left, parent.right = merged[i], parent.left
        return merged[0]

    # ── mutation ────────────────────────────────────────────────────────────────────────
    def insert(self, value: Any) -> None:
        """Insert ``value`` (duplicates allowed)."""
        kind = _kind(value)
        with self._lock:
            if self._kind is None:
                self._kind = kind
            elif kind != self._kind:
                raise SkewHeapError(f"value kind {kind!r} does not match heap kind {self._kind!r}")
            self._root = self._meld(self._root, _Node(value))
            self._size += 1

    def extract_min(self) -> Any:
        """Remove and return the minimum value; raises if the heap is empty."""
        with self._lock:
            if self._root is None:
                raise SkewHeapError("extract_min() on an empty heap")
            root = self._root
            self._root = self._meld(root.left, root.right)
            self._size -= 1
            if self._size == 0:
                self._kind = None
            return root.key

    def meld(self, other: SkewHeap) -> None:
        """Union ``other`` into this heap; ``other`` is emptied (its nodes move here)."""
        if not isinstance(other, SkewHeap):
            raise SkewHeapError("can only meld another SkewHeap")
        if other is self:
            return
        # Acquire both locks in a consistent (id) order so concurrent a.meld(b) / b.meld(a)
        # can never deadlock via lock-ordering inversion.
        first, second = (self, other) if id(self) <= id(other) else (other, self)
        with first._lock:
            with second._lock:
                if self._root is not None and other._root is not None and self._kind != other._kind:
                    raise SkewHeapError(
                        f"cannot meld heaps of kinds {self._kind!r} and {other._kind!r}"
                    )
                self._root = self._meld(self._root, other._root)
                self._size += other._size
                if self._kind is None:
                    self._kind = other._kind
                other._root = None
                other._size = 0
                other._kind = None

    def reset(self) -> None:
        """Empty the heap."""
        with self._lock:
            self._root = None
            self._size = 0
            self._kind = None

    # ── inspection ──────────────────────────────────────────────────────────────────────
    def peek_min(self) -> Any:
        """Return the minimum value without removing it; raises if empty."""
        with self._lock:
            if self._root is None:
                raise SkewHeapError("peek_min() on an empty heap")
            return self._root.key

    def find_min(self) -> Any:
        return self.peek_min()

    def is_empty(self) -> bool:
        return self._size == 0

    def keys_sorted(self) -> list:
        """All values in ascending order (read-only; does not modify the heap)."""
        with self._lock:
            out: list = []
            stack = [self._root]
            while stack:
                node = stack.pop()
                if node is not None:
                    out.append(node.key)
                    stack.append(node.left)
                    stack.append(node.right)
            out.sort()
            return out

    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    @property
    def kind(self) -> str | None:
        return self._kind

    def stats(self) -> dict:
        """Summary: ``size`` / ``min`` (or ``None`` if empty) / ``kind``."""
        with self._lock:
            return {
                "size": self._size,
                "min": self._root.key if self._root is not None else None,
                "kind": self._kind,
            }
