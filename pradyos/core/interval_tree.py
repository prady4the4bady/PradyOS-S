"""Phase 137 — Sovereign Interval Tree (Cormen–Leiserson–Rivest–Stein, augmented BST).

A **dynamic set of intervals supporting overlap and stabbing queries** — a new capability for
the platform. Intervals ``[low, high]`` (endpoints inclusive) are stored in a binary search
tree keyed by ``low``, and **every node is augmented with ``max``** — the largest ``high``
endpoint anywhere in its subtree. That single augmentation is what makes interval search fast:
to find an interval overlapping a query you descend into the left child whenever its subtree
``max`` can still reach the query's low, otherwise right, pruning whole subtrees.

Operations: ``insert``, ``remove``, ``contains``, ``overlap_any(low, high)`` (one overlapping
interval, CLRS interval-search), ``overlap(low, high)`` (all of them, with subtree-``max``
pruning), ``stab(point)`` (intervals containing a point), and ``count``. Two intervals
``[a,b]``, ``[c,d]`` overlap iff ``a ≤ d and c ≤ b``.

This is *different* from the platform's point-keyed ordered maps (Splay/P133, Treap/P113, Skip
List/P78): an interval tree answers **range-intersection** queries via the subtree-``max``
augmentation. Every operation here is **iterative** (the augmentation is recomputed along the
recorded path), so the structure is immune to Python recursion limits even on adversarial
sorted-`low` inserts. Pure stdlib; thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

from typing import Any

import threading

_NEG_INF = float("-inf")


class IntervalTreeError(Exception):
    """Raised for an invalid Interval-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class _Node:
    __slots__ = ("low", "high", "max", "left", "right")

    def __init__(self, low: Any, high: Any) -> None:
        self.low = low
        self.high = high
        self.max = high                 # max high endpoint in this subtree
        self.left: "_Node | None" = None
        self.right: "_Node | None" = None


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _submax(node: "_Node | None") -> float:
    return node.max if node is not None else _NEG_INF


def _recompute(node: _Node) -> None:
    m = node.high
    lm = _submax(node.left)
    rm = _submax(node.right)
    if lm > m:
        m = lm
    if rm > m:
        m = rm
    node.max = m


class IntervalTree:
    """Augmented BST of intervals (subtree-max) for overlap / stabbing queries."""

    def __init__(self) -> None:
        self._root: _Node | None = None
        self._size = 0
        self._lock = threading.Lock()

    # ── validation ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _check_interval(low: Any, high: Any) -> None:
        if not _num(low) or not _num(high):
            raise IntervalTreeError("low and high must be numbers (not bool)")
        if low > high:
            raise IntervalTreeError(f"low ({low}) must be <= high ({high})")

    # ── mutation (iterative; max recomputed along the path) ──────────────────────────
    def insert(self, low: Any, high: Any) -> None:
        """Insert interval ``[low, high]`` (duplicates allowed)."""
        self._check_interval(low, high)
        with self._lock:
            new = _Node(low, high)
            if self._root is None:
                self._root = new
                self._size = 1
                return
            path = []
            cur = self._root
            while True:
                path.append(cur)
                if low < cur.low:
                    if cur.left is None:
                        cur.left = new
                        break
                    cur = cur.left
                else:
                    if cur.right is None:
                        cur.right = new
                        break
                    cur = cur.right
            self._size += 1
            for node in reversed(path):          # bottom-up max fixup
                _recompute(node)

    def remove(self, low: Any, high: Any) -> bool:
        """Remove one interval equal to ``[low, high]``; returns whether it was present."""
        self._check_interval(low, high)
        with self._lock:
            path = []
            cur = self._root
            while cur is not None and not (cur.low == low and cur.high == high):
                path.append(cur)
                cur = cur.left if low < cur.low else cur.right
            if cur is None:
                return False
            target = cur
            if target.left is not None and target.right is not None:
                # two children: lift the in-order successor's interval, then delete it
                path.append(target)
                succ_parent = target
                succ = target.right
                while succ.left is not None:
                    path.append(succ)
                    succ_parent = succ
                    succ = succ.left
                target.low, target.high = succ.low, succ.high
                child = succ.right
                if succ_parent.left is succ:
                    succ_parent.left = child
                else:
                    succ_parent.right = child
            else:
                child = target.left if target.left is not None else target.right
                if not path:
                    self._root = child
                else:
                    parent = path[-1]
                    if parent.left is target:
                        parent.left = child
                    else:
                        parent.right = child
            self._size -= 1
            for node in reversed(path):          # bottom-up max fixup
                _recompute(node)
            return True

    def reset(self) -> None:
        """Empty the tree."""
        with self._lock:
            self._root = None
            self._size = 0

    # ── queries ──────────────────────────────────────────────────────────────────────
    @staticmethod
    def _overlaps(node: _Node, low: Any, high: Any) -> bool:
        return node.low <= high and low <= node.high

    def contains(self, low: Any, high: Any) -> bool:
        """Whether the exact interval ``[low, high]`` is present."""
        self._check_interval(low, high)
        with self._lock:
            cur = self._root
            while cur is not None:
                if cur.low == low and cur.high == high:
                    return True
                cur = cur.left if low < cur.low else cur.right
            return False

    def overlap_any(self, low: Any, high: Any) -> Any:
        """Return one stored interval overlapping ``[low, high]`` as ``(low, high)``, or ``None``."""
        self._check_interval(low, high)
        with self._lock:
            cur = self._root
            while cur is not None and not self._overlaps(cur, low, high):
                if cur.left is not None and cur.left.max >= low:
                    cur = cur.left
                else:
                    cur = cur.right
            return (cur.low, cur.high) if cur is not None else None

    def overlap(self, low: Any, high: Any) -> list:
        """All stored intervals overlapping ``[low, high]``, sorted (subtree-max pruning)."""
        self._check_interval(low, high)
        with self._lock:
            out: list = []
            stack = [self._root]
            while stack:
                node = stack.pop()
                if node is None or node.max < low:   # prune: no high in subtree reaches `low`
                    continue
                if node.left is not None:
                    stack.append(node.left)
                if node.low <= high:                 # right lows ≥ node.low; skip if node.low > high
                    if self._overlaps(node, low, high):
                        out.append((node.low, node.high))
                    if node.right is not None:
                        stack.append(node.right)
                elif self._overlaps(node, low, high):
                    out.append((node.low, node.high))
            out.sort()
            return out

    def stab(self, point: Any) -> list:
        """All stored intervals containing ``point`` (``low ≤ point ≤ high``), sorted."""
        if not _num(point):
            raise IntervalTreeError("point must be a number (not bool)")
        return self.overlap(point, point)

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    @property
    def max_endpoint(self) -> Any:
        return self._root.max if self._root is not None else None

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

    def stats(self) -> dict:
        """Summary: ``size`` / ``max_endpoint`` (or ``None``) / ``height``."""
        with self._lock:
            return {
                "size": self._size,
                "max_endpoint": self._root.max if self._root is not None else None,
                "height": self._height(),
            }
