"""Phase 142 — Sovereign Aho-Corasick (Aho & Corasick, 1975).

A **multi-pattern string-matching automaton** that finds *all* occurrences of *all* patterns in
a text in a single ``O(text + matches)`` pass — a new capability for the platform. It is the
generalisation of KMP from one pattern to a whole dictionary.

Construction. The patterns are inserted into a **trie**; then a breadth-first sweep adds:
  * a **failure link** at each node — pointing to the deepest node whose string is a proper
    suffix of this node's string and is itself a trie node, so that on a mismatch the automaton
    falls back without ever re-scanning the text (KMP's failure function, over the trie);
  * an **output set** — the patterns ending at this node *plus* those reachable through the
    failure chain, so overlapping and nested matches are all reported.

``search(text)`` then walks the automaton one character at a time, emitting ``(pattern,
end_index)`` for every match. This is *different* from the platform's single-string indexes
(Suffix Array/P141, Radix Tree/P140): it matches a *dictionary* of patterns against a stream
at once — the structure behind intrusion detection and content filtering. The automaton
**auto-builds** on the first search after a pattern is added. Pure stdlib (``collections.deque``);
thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any


class AhoCorasickError(Exception):
    """Raised for an invalid Aho-Corasick operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class _Node:
    __slots__ = ("children", "fail", "own", "outputs")

    def __init__(self) -> None:
        self.children: dict[str, _Node] = {}
        self.fail: "_Node | None" = None
        self.own: list = []                  # patterns ending exactly at this node
        self.outputs: list = []              # patterns matching here (own + via failure chain)


class AhoCorasick:
    """Aho-Corasick multi-pattern matching automaton (trie + failure/output links)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._root = _Node()
        self._patterns: set = set()
        self._dirty = False                  # True when a pattern was added since the last build

    # ── add ──────────────────────────────────────────────────────────────────────────────
    def add(self, pattern: Any) -> bool:
        """Add ``pattern`` to the dictionary; returns whether it was new (duplicates ignored)."""
        if not isinstance(pattern, str):
            raise AhoCorasickError("pattern must be a string")
        if pattern == "":
            raise AhoCorasickError("pattern must be non-empty")
        with self._lock:
            if pattern in self._patterns:
                return False
            self._patterns.add(pattern)
            node = self._root
            for ch in pattern:
                nxt = node.children.get(ch)
                if nxt is None:
                    nxt = _Node()
                    node.children[ch] = nxt
                node = nxt
            node.own.append(pattern)
            self._dirty = True
            return True

    def add_many(self, patterns: Any) -> int:
        """Add many patterns; returns the number newly added."""
        try:
            items = list(patterns)
        except TypeError as exc:
            raise AhoCorasickError("patterns must be iterable") from exc
        added = 0
        for p in items:
            if self.add(p):
                added += 1
        return added

    # ── build (BFS failure + output links) ────────────────────────────────────────────
    def _build_locked(self) -> None:
        root = self._root
        root.fail = root
        root.outputs = list(root.own)
        q: deque = deque()
        for child in root.children.values():
            child.fail = root
            q.append(child)
        while q:
            u = q.popleft()
            u.outputs = list(u.own)
            u.outputs.extend(u.fail.outputs)   # u.fail is shallower → already finalised
            for ch, v in u.children.items():
                f = u.fail
                while f is not root and ch not in f.children:
                    f = f.fail
                v.fail = f.children[ch] if (ch in f.children and f.children[ch] is not v) else root
                q.append(v)
        self._dirty = False

    def build(self) -> None:
        """Finalise the failure and output links (otherwise done lazily on first search)."""
        with self._lock:
            self._build_locked()

    # ── search ──────────────────────────────────────────────────────────────────────────
    def search(self, text: Any) -> list:
        """All matches as sorted ``(pattern, end_index)`` pairs (``end_index`` 0-based inclusive)."""
        if not isinstance(text, str):
            raise AhoCorasickError("text must be a string")
        with self._lock:
            if self._dirty:
                self._build_locked()
            root = self._root
            node = root
            out: list = []
            for i, ch in enumerate(text):
                while node is not root and ch not in node.children:
                    node = node.fail
                node = node.children.get(ch, root)
                for p in node.outputs:
                    out.append((p, i))
            out.sort(key=lambda m: (m[1], m[0]))
            return out

    def count(self, text: Any) -> int:
        """Total number of (pattern, position) matches in ``text``."""
        return len(self.search(text))

    def contains_any(self, text: Any) -> bool:
        """Whether any pattern occurs in ``text``."""
        if not isinstance(text, str):
            raise AhoCorasickError("text must be a string")
        with self._lock:
            if self._dirty:
                self._build_locked()
            root = self._root
            node = root
            for ch in text:
                while node is not root and ch not in node.children:
                    node = node.fail
                node = node.children.get(ch, root)
                if node.outputs:
                    return True
            return False

    def reset(self) -> None:
        """Empty the automaton."""
        with self._lock:
            self._root = _Node()
            self._patterns = set()
            self._dirty = False

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self._patterns)

    @property
    def num_patterns(self) -> int:
        return len(self._patterns)

    @property
    def built(self) -> bool:
        return not self._dirty

    def patterns(self) -> list:
        with self._lock:
            return sorted(self._patterns)

    def _count_nodes(self) -> int:
        n = 0
        stack = [self._root]
        while stack:
            node = stack.pop()
            n += 1
            stack.extend(node.children.values())
        return n

    def stats(self) -> dict:
        """Summary: ``num_patterns`` / ``num_nodes`` / ``built``."""
        with self._lock:
            return {"num_patterns": len(self._patterns), "num_nodes": self._count_nodes(),
                    "built": not self._dirty}
