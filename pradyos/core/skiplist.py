"""Phase 78 — Sovereign Skip List (ordered probabilistic index).

A skip list is an ordered key→value map that gives expected O(log n) search,
insert, and delete without the rebalancing machinery of a tree. Each node is
linked at several levels; a node's height is chosen randomly (geometric, with
``p = 0.5`` up to ``max_level``), so higher express lanes let a search skip over
large spans and drop down as it nears the key.

Because the bottom level is a plain sorted linked list, ordered operations —
:meth:`range_query` over an inclusive ``[lo, hi]`` window and in-order
iteration — fall out for free. The RNG is seedable so level generation can be
made deterministic in tests. Pure stdlib (``random``); thread-safe via a single
non-reentrant ``threading.Lock``.
"""

from __future__ import annotations

import random
import threading
from typing import Any


class _Node:
    __slots__ = ("key", "value", "forward")

    def __init__(self, key, value, level: int) -> None:
        self.key = key
        self.value = value
        self.forward: list = [None] * (level + 1)


class SkipList:
    """An ordered key→value map backed by a probabilistic skip list (stdlib only)."""

    def __init__(self, max_level: int = 16, p: float = 0.5, seed: int | None = None) -> None:
        if max_level < 1:
            raise ValueError("max_level must be >= 1")
        if not 0.0 < p < 1.0:
            raise ValueError("p must be between 0 and 1 (exclusive)")
        self._max_level = int(max_level)
        self._p = float(p)
        self._head = _Node(None, None, self._max_level)  # sentinel; forward[0.._max_level-1]
        self._level = 0  # highest level index currently in use
        self._size = 0
        self._rng = random.Random(seed)
        self._lock = threading.Lock()

    # ── internal (assume lock held) ──────────────────────────────────────────
    def _random_level(self) -> int:
        lvl = 0
        while self._rng.random() < self._p and lvl < self._max_level - 1:
            lvl += 1
        return lvl

    # ── mutation ──────────────────────────────────────────────────────────────
    def insert(self, key, value: Any) -> None:
        """Insert ``key`` → ``value``; an existing key's value is overwritten."""
        if key is None:
            raise ValueError("key must not be None")
        with self._lock:
            update = [self._head] * self._max_level
            node = self._head
            for i in range(self._level, -1, -1):
                while node.forward[i] is not None and node.forward[i].key < key:
                    node = node.forward[i]
                update[i] = node
            nxt = node.forward[0]
            if nxt is not None and nxt.key == key:
                nxt.value = value  # overwrite, size unchanged
                return
            lvl = self._random_level()
            if lvl > self._level:
                for i in range(self._level + 1, lvl + 1):
                    update[i] = self._head
                self._level = lvl
            fresh = _Node(key, value, lvl)
            for i in range(lvl + 1):
                fresh.forward[i] = update[i].forward[i]
                update[i].forward[i] = fresh
            self._size += 1

    def delete(self, key) -> bool:
        """Remove ``key``. Returns True if it existed, else False."""
        if key is None:
            raise ValueError("key must not be None")
        with self._lock:
            update = [self._head] * self._max_level
            node = self._head
            for i in range(self._level, -1, -1):
                while node.forward[i] is not None and node.forward[i].key < key:
                    node = node.forward[i]
                update[i] = node
            target = node.forward[0]
            if target is None or target.key != key:
                return False
            for i in range(self._level + 1):
                if update[i].forward[i] is not target:
                    break
                update[i].forward[i] = target.forward[i]
            while self._level > 0 and self._head.forward[self._level] is None:
                self._level -= 1
            self._size -= 1
            return True

    def clear(self) -> None:
        """Drop all entries."""
        with self._lock:
            self._head = _Node(None, None, self._max_level)
            self._level = 0
            self._size = 0

    # ── queries ─────────────────────────────────────────────────────────────
    def search(self, key) -> Any | None:
        """Return the value for ``key``, or None if absent."""
        if key is None:
            raise ValueError("key must not be None")
        with self._lock:
            node = self._head
            for i in range(self._level, -1, -1):
                while node.forward[i] is not None and node.forward[i].key < key:
                    node = node.forward[i]
            nxt = node.forward[0]
            if nxt is not None and nxt.key == key:
                return nxt.value
            return None

    def __contains__(self, key) -> bool:
        return self.search(key) is not None

    def range_query(self, lo, hi) -> list[tuple]:
        """All ``(key, value)`` pairs with ``lo <= key <= hi``, in ascending order.

        An empty list is returned when ``lo > hi`` or no key falls in range.
        """
        if lo is None or hi is None:
            raise ValueError("lo and hi must not be None")
        with self._lock:
            node = self._head
            for i in range(self._level, -1, -1):
                while node.forward[i] is not None and node.forward[i].key < lo:
                    node = node.forward[i]
            node = node.forward[0]
            result: list[tuple] = []
            while node is not None and node.key <= hi:
                result.append((node.key, node.value))
                node = node.forward[0]
            return result

    def items(self) -> list[tuple]:
        """All ``(key, value)`` pairs in ascending key order."""
        with self._lock:
            result: list[tuple] = []
            node = self._head.forward[0]
            while node is not None:
                result.append((node.key, node.value))
                node = node.forward[0]
            return result

    def __len__(self) -> int:
        with self._lock:
            return self._size

    def stats(self) -> dict:
        """JSON-serialisable snapshot: size, levels in use, configured max level."""
        with self._lock:
            return {
                "size": self._size,
                "level_count": self._level + 1,
                "max_level": self._max_level,
            }
