"""Phase 143 — Sovereign Binary (XOR) Trie.

A **bitwise trie over fixed-width integers** that answers **maximum-XOR** queries greedily — a
new capability for the platform. Each integer is stored as a root-to-leaf path of its bits from
the most significant down (`width` levels, default 32). To find `max(q ^ x)` over all stored
`x`, descend from the root preferring, at every level, the child whose bit is the *opposite* of
`q`'s bit — that maximises that bit of the XOR — so one `O(width)` descent gives the answer.

With per-node counts (a multiset) it also supports:
  * `min_xor(q)` — prefer the *same* bit at each level;
  * `count_xor_less(q, k)` — how many stored `x` have `q ^ x < k` (the building block of XOR
    range queries): at a `k`-bit of 1, every value on the XOR-0 branch is already below `k`, so
    its whole subtree count is added and the search continues down the XOR-1 branch; at a
    `k`-bit of 0 only the XOR-0 branch can stay below `k`;
  * `insert` / `remove` (decrementing counts, pruning emptied subtrees) / `contains`.

This is *different* in mechanism from the platform's character trie (P83) and radix tree
(P140): it is a fixed-depth *binary* trie keyed on bit position — the structure behind
max-XOR-pair and XOR-range problems. Pure stdlib; thread-safe via a single ``threading.Lock``;
deterministic. Every operation is iterative (``width`` levels, no recursion).
"""

from __future__ import annotations

import threading
from typing import Any


class XorTrieError(Exception):
    """Raised for an invalid XOR-trie operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class _Node:
    __slots__ = ("children", "count")

    def __init__(self) -> None:
        self.children: list = [None, None]  # children[0], children[1]
        self.count = 0  # number of stored values passing through this node


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class XorTrie:
    """Fixed-width binary trie for max/min-XOR and XOR-range queries (a multiset of ints)."""

    def __init__(self, width: int = 32) -> None:
        if not _is_int(width) or not (1 <= width <= 256):
            raise XorTrieError("width must be an int in [1, 256]")
        self._width = width
        self._limit = 1 << width
        self._root = _Node()
        self._size = 0
        self._lock = threading.Lock()

    def _check_value(self, value: Any, what: str = "value") -> int:
        if not _is_int(value) or not (0 <= value < self._limit):
            raise XorTrieError(f"{what} must be an int in [0, 2^{self._width})")
        return value

    # ── mutation ────────────────────────────────────────────────────────────────────────
    def insert(self, value: Any) -> None:
        """Insert ``value`` (a multiset — duplicates increment its count)."""
        with self._lock:
            self._check_value(value)
            node = self._root
            for pos in range(self._width - 1, -1, -1):
                b = (value >> pos) & 1
                if node.children[b] is None:
                    node.children[b] = _Node()
                node = node.children[b]
                node.count += 1
            self._size += 1

    def _contains_locked(self, value: int) -> bool:
        node = self._root
        for pos in range(self._width - 1, -1, -1):
            child = node.children[(value >> pos) & 1]
            if child is None or child.count == 0:
                return False
            node = child
        return True

    def remove(self, value: Any) -> bool:
        """Remove one occurrence of ``value``; returns whether it was present."""
        with self._lock:
            self._check_value(value)
            if not self._contains_locked(value):
                return False
            node = self._root
            path = []
            for pos in range(self._width - 1, -1, -1):
                b = (value >> pos) & 1
                path.append((node, b))
                node = node.children[b]
                node.count -= 1
            for parent, b in reversed(path):  # prune subtrees that emptied out
                if parent.children[b].count == 0:
                    parent.children[b] = None
            self._size -= 1
            return True

    def contains(self, value: Any) -> bool:
        with self._lock:
            self._check_value(value)
            return self._contains_locked(value)

    def __contains__(self, value: Any) -> bool:
        return self.contains(value)

    def reset(self, width: int | None = None) -> None:
        """Empty the trie; optionally reconfigure ``width``."""
        with self._lock:
            nw = self._width if width is None else width
            if not _is_int(nw) or not (1 <= nw <= 256):
                raise XorTrieError("width must be an int in [1, 256]")
            self._width = nw
            self._limit = 1 << nw
            self._root = _Node()
            self._size = 0

    # ── queries ──────────────────────────────────────────────────────────────────────
    def max_xor(self, query: Any) -> int:
        """``max(query ^ x)`` over all stored ``x``; raises if empty."""
        with self._lock:
            self._check_value(query, "query")
            if self._size == 0:
                raise XorTrieError("max_xor on an empty trie")
            node, result = self._root, 0
            for pos in range(self._width - 1, -1, -1):
                qb = (query >> pos) & 1
                opp = node.children[1 - qb]
                if opp is not None and opp.count > 0:
                    result |= 1 << pos
                    node = opp
                else:
                    node = node.children[qb]
            return result

    def min_xor(self, query: Any) -> int:
        """``min(query ^ x)`` over all stored ``x``; raises if empty."""
        with self._lock:
            self._check_value(query, "query")
            if self._size == 0:
                raise XorTrieError("min_xor on an empty trie")
            node, result = self._root, 0
            for pos in range(self._width - 1, -1, -1):
                qb = (query >> pos) & 1
                same = node.children[qb]
                if same is not None and same.count > 0:
                    node = same
                else:
                    result |= 1 << pos
                    node = node.children[1 - qb]
            return result

    def count_xor_less(self, query: Any, k: Any) -> int:
        """Number of stored ``x`` with ``(query ^ x) < k``."""
        with self._lock:
            self._check_value(query, "query")
            if not _is_int(k):
                raise XorTrieError("k must be an int")
            if k <= 0:
                return 0
            if k >= self._limit:
                return self._size
            node, cnt = self._root, 0
            for pos in range(self._width - 1, -1, -1):
                if node is None:
                    break
                qb = (query >> pos) & 1
                kb = (k >> pos) & 1
                if kb == 1:
                    xor0 = node.children[qb]  # XOR-bit 0 here → strictly below k
                    if xor0 is not None:
                        cnt += xor0.count
                    node = node.children[qb ^ 1]  # follow the XOR-bit-1 branch
                else:
                    node = node.children[qb]  # only XOR-bit 0 can stay below k
            return cnt

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    @property
    def width(self) -> int:
        return self._width

    def _count_nodes(self) -> int:
        n = 0
        stack = [self._root]
        while stack:
            node = stack.pop()
            n += 1
            for c in node.children:
                if c is not None:
                    stack.append(c)
        return n

    def stats(self) -> dict:
        """Summary: ``size`` / ``width`` / ``num_nodes``."""
        with self._lock:
            return {"size": self._size, "width": self._width, "num_nodes": self._count_nodes()}
