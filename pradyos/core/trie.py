"""Phase 83 — Sovereign Trie.

A prefix tree (trie) mapping string keys to arbitrary values. Each node owns a
``children`` map (one entry per next character) and an ``is_end`` flag marking
the terminus of a stored key; the value rides on the terminal node. This gives
O(len(key)) insert / search / delete and an O(len(prefix) + matches) prefix scan
(``starts_with``) — the natural primitive behind autocomplete and "keys under a
namespace" lookups.

Traversals (``starts_with`` / ``to_dict``) are iterative with an explicit stack
so a pathologically long key can never blow the recursion limit. Deleting a key
prunes the now-dangling chain of childless, non-terminal nodes back up toward the
root. Pure stdlib — no third-party dependencies. Thread-safe via a single
``threading.Lock``; the public surface acquires it, and internal helpers that run
under the lock never re-acquire it (the lock is non-reentrant).
"""

from __future__ import annotations

import threading
from typing import Any


class KeyNotFoundError(Exception):
    """Raised when a key is queried that is not stored in the trie.

    The ``key`` attribute holds the offending key string.
    """

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"key not found: {key!r}")


class _Node:
    __slots__ = ("children", "is_end", "value")

    def __init__(self) -> None:
        self.children: dict[str, _Node] = {}
        self.is_end = False
        self.value: Any = None


class SovereignTrie:
    """A string-keyed prefix tree with values (stdlib only)."""

    def __init__(self) -> None:
        self._root = _Node()
        self._size = 0      # number of stored keys
        self._nodes = 1     # number of nodes, including the root
        self._lock = threading.Lock()

    # ── internal (callers already hold the lock) ─────────────────────────────
    def _find_node(self, key: str) -> _Node | None:
        node = self._root
        for ch in key:
            nxt = node.children.get(ch)
            if nxt is None:
                return None
            node = nxt
        return node

    def _collect_locked(self, start: _Node, prefix: str) -> list[tuple[str, Any]]:
        """Iterative pre-order walk yielding ``(key, value)`` in sorted order."""
        out: list[tuple[str, Any]] = []
        stack = [(start, prefix)]
        while stack:
            node, acc = stack.pop()
            if node.is_end:
                out.append((acc, node.value))
            # push children reverse-sorted so they pop in ascending order
            for ch in sorted(node.children, reverse=True):
                stack.append((node.children[ch], acc + ch))
        out.sort(key=lambda kv: kv[0])
        return out

    # ── mutation ──────────────────────────────────────────────────────────────
    def insert(self, key: str, value: Any = True) -> None:
        """Store ``key`` with ``value`` (overwriting any existing value)."""
        if not isinstance(key, str) or key == "":
            raise ValueError("key must be a non-empty string")
        with self._lock:
            node = self._root
            for ch in key:
                nxt = node.children.get(ch)
                if nxt is None:
                    nxt = _Node()
                    node.children[ch] = nxt
                    self._nodes += 1
                node = nxt
            if not node.is_end:
                self._size += 1
            node.is_end = True
            node.value = value

    def delete(self, key: str) -> bool:
        """Remove ``key``. Returns True if it existed, False otherwise.

        Prunes any nodes that become childless and non-terminal as a result."""
        if not isinstance(key, str):
            raise ValueError("key must be a string")
        with self._lock:
            path: list[_Node] = [self._root]
            node = self._root
            for ch in key:
                nxt = node.children.get(ch)
                if nxt is None:
                    return False
                path.append(nxt)
                node = nxt
            if not node.is_end:
                return False
            node.is_end = False
            node.value = None
            self._size -= 1
            # prune dangling nodes from the leaf upward
            for depth in range(len(key), 0, -1):
                child = path[depth]
                if child.children or child.is_end:
                    break
                parent = path[depth - 1]
                del parent.children[key[depth - 1]]
                self._nodes -= 1
            return True

    def clear(self) -> None:
        """Remove all keys."""
        with self._lock:
            self._root = _Node()
            self._size = 0
            self._nodes = 1

    # ── queries ─────────────────────────────────────────────────────────────
    def search(self, key: str) -> Any:
        """Return the value stored at ``key``. Raises :class:`KeyNotFoundError`."""
        if not isinstance(key, str):
            raise ValueError("key must be a string")
        with self._lock:
            node = self._find_node(key)
            if node is None or not node.is_end:
                raise KeyNotFoundError(key)
            return node.value

    def contains(self, key: str) -> bool:
        """True if ``key`` is stored (no exception)."""
        if not isinstance(key, str):
            return False
        with self._lock:
            node = self._find_node(key)
            return node is not None and node.is_end

    def starts_with(self, prefix: str) -> list[tuple[str, Any]]:
        """Every ``(key, value)`` whose key starts with ``prefix``, key-sorted.

        An empty ``prefix`` returns all keys; an absent prefix returns ``[]``."""
        if not isinstance(prefix, str):
            raise ValueError("prefix must be a string")
        with self._lock:
            start = self._find_node(prefix)
            if start is None:
                return []
            return self._collect_locked(start, prefix)

    def keys(self) -> list[str]:
        """All stored keys, sorted."""
        with self._lock:
            return [k for k, _ in self._collect_locked(self._root, "")]

    def __len__(self) -> int:
        with self._lock:
            return self._size

    # ── serialization ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        """A JSON-serialisable snapshot: counts plus the flat key→value map."""
        with self._lock:
            keys = dict(self._collect_locked(self._root, ""))
            return {"size": self._size, "nodes": self._nodes, "keys": keys}

    def stats(self) -> dict:
        """Compact snapshot of key and node counts."""
        with self._lock:
            return {"size": self._size, "nodes": self._nodes}
