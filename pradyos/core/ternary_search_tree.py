"""Phase 164 — Sovereign Ternary Search Tree (Bentley & Sedgewick, 1997).

A **string symbol table** that stores keys character-by-character in a *ternary* BST: each node
holds one character and three children — ``lo`` / ``eq`` / ``hi``. A search compares the current
query character against the node's character and branches **left** (`lo`, smaller char) or
**right** (`hi`, larger char) on a mismatch, or descends through **`eq`** on a match (advancing to
the next query character). This blends a trie's prefix structure with a BST's space efficiency,
giving `O(|key| + tree-depth)` `insert` / `contains` / `delete`, plus **prefix enumeration**
(`keys_with_prefix`) and **longest-prefix-of** queries.

It is distinct from the platform's other string structures — the edge-compressed Radix Tree/P140
(Patricia), the bit-tries (XOR Trie/P143), and the suffix structures — being a *comparison* trie
over characters. Deletion is lazy (a key's terminal node is unmarked), so re-insertion is `O(1)`
extra. Every descent and the prefix `collect` use explicit loops / a stack — **no recursion**, so a
degenerate (sorted-insert) character-BST cannot overflow. Pure stdlib; thread-safe via a single
``threading.Lock``; deterministic.
"""

from __future__ import annotations

import threading
from typing import Any


class TernarySearchTreeError(Exception):
    """Raised for an invalid ternary-search-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class _TSTNode:
    __slots__ = ("ch", "lo", "eq", "hi", "is_end")

    def __init__(self, ch: str) -> None:
        self.ch = ch
        self.lo: _TSTNode | None = None
        self.eq: _TSTNode | None = None
        self.hi: _TSTNode | None = None
        self.is_end = False


class TernarySearchTree:
    """String symbol table over a character-BST: insert/contains/delete + prefix / longest-prefix."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._root: _TSTNode | None = None
        self._size = 0

    @staticmethod
    def _check_key(key: Any, *, allow_empty: bool) -> None:
        if not isinstance(key, str):
            raise TernarySearchTreeError("key must be a string")
        if not allow_empty and key == "":
            raise TernarySearchTreeError("key must be a non-empty string")

    # ── insert ───────────────────────────────────────────────────────────────────────────
    def insert(self, key: str) -> bool:
        """Insert ``key``; return True iff it was newly added."""
        self._check_key(key, allow_empty=False)
        with self._lock:
            if self._root is None:
                self._root = _TSTNode(key[0])
            node = self._root
            i = 0
            while True:
                c = key[i]
                if c < node.ch:
                    if node.lo is None:
                        node.lo = _TSTNode(c)
                    node = node.lo
                elif c > node.ch:
                    if node.hi is None:
                        node.hi = _TSTNode(c)
                    node = node.hi
                else:
                    if i == len(key) - 1:
                        if node.is_end:
                            return False
                        node.is_end = True
                        self._size += 1
                        return True
                    i += 1
                    if node.eq is None:
                        node.eq = _TSTNode(key[i])
                    node = node.eq

    # ── contains / delete ─────────────────────────────────────────────────────────────────
    def _find(self, key: str) -> _TSTNode | None:
        node = self._root
        i = 0
        while node is not None:
            c = key[i]
            if c < node.ch:
                node = node.lo
            elif c > node.ch:
                node = node.hi
            else:
                if i == len(key) - 1:
                    return node
                i += 1
                node = node.eq
        return None

    def contains(self, key: str) -> bool:
        """True iff ``key`` is in the table."""
        self._check_key(key, allow_empty=True)
        with self._lock:
            if key == "":
                return False
            node = self._find(key)
            return node is not None and node.is_end

    def delete(self, key: str) -> bool:
        """Delete ``key`` (lazy: unmark its terminal node); return True iff it was present."""
        self._check_key(key, allow_empty=True)
        with self._lock:
            if key == "":
                return False
            node = self._find(key)
            if node is None or not node.is_end:
                return False
            node.is_end = False
            self._size -= 1
            return True

    # ── prefix queries ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def _collect(start: _TSTNode | None, prefix: str) -> list:
        out = []
        if start is None:
            return out
        stack = [(start, prefix)]
        while stack:
            node, pre = stack.pop()
            if node.lo is not None:
                stack.append((node.lo, pre))
            if node.hi is not None:
                stack.append((node.hi, pre))
            if node.eq is not None:
                stack.append((node.eq, pre + node.ch))
            if node.is_end:
                out.append(pre + node.ch)
        return out

    def _find_prefix_node(self, prefix: str) -> _TSTNode | None:
        node = self._root
        i = 0
        while node is not None:
            c = prefix[i]
            if c < node.ch:
                node = node.lo
            elif c > node.ch:
                node = node.hi
            else:
                if i == len(prefix) - 1:
                    return node
                i += 1
                node = node.eq
        return None

    def keys_with_prefix(self, prefix: str) -> list:
        """Sorted list of all keys having ``prefix`` as a prefix (empty prefix → all keys)."""
        self._check_key(prefix, allow_empty=True)
        with self._lock:
            if prefix == "":
                return sorted(self._collect(self._root, ""))
            p = self._find_prefix_node(prefix)
            if p is None:
                return []
            out = []
            if p.is_end:
                out.append(prefix)
            out.extend(self._collect(p.eq, prefix))
            return sorted(out)

    def longest_prefix_of(self, query: str) -> str | None:
        """The longest key that is a prefix of ``query`` (``None`` if no key is a prefix)."""
        self._check_key(query, allow_empty=True)
        with self._lock:
            node = self._root
            i = 0
            length = 0
            while node is not None and i < len(query):
                c = query[i]
                if c < node.ch:
                    node = node.lo
                elif c > node.ch:
                    node = node.hi
                else:
                    i += 1
                    if node.is_end:
                        length = i
                    node = node.eq
            return query[:length] if length > 0 else None

    def keys(self) -> list:
        """All keys in sorted order."""
        with self._lock:
            return sorted(self._collect(self._root, ""))

    def reset(self) -> None:
        """Empty the table."""
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
        """Summary: ``size`` / ``nodes`` (total tree nodes)."""
        with self._lock:
            nodes = 0
            if self._root is not None:
                stack = [self._root]
                while stack:
                    node = stack.pop()
                    nodes += 1
                    if node.lo is not None:
                        stack.append(node.lo)
                    if node.eq is not None:
                        stack.append(node.eq)
                    if node.hi is not None:
                        stack.append(node.hi)
            return {"size": self._size, "nodes": nodes}
