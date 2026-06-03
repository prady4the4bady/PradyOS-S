"""Phase 140 — Sovereign Radix Tree / Patricia Trie (Morrison, 1968).

A **path-compressed prefix tree** for string keys — a new capability for the platform and a
more compact cousin of the plain Trie (P83). Where a trie stores one character per edge, a
radix tree **labels each edge with a whole substring** and collapses any chain of single-child
nodes, so the number of nodes is bounded by the number of *distinguishing* prefixes rather than
the total key length. It is the structure behind IP routing tables and autocomplete.

Operations:
  * ``insert(key, value)`` — walks the key against edge labels, **splitting** an edge when the
    key diverges partway along it;
  * ``search(key)`` — exact lookup;
  * ``delete(key)`` — clears the key and **re-merges** a now-only-child node back into its
    parent so the compression invariant is preserved;
  * ``prefix_search(prefix)`` — every stored key under a prefix (autocomplete);
  * ``longest_prefix(query)`` — the longest stored key that is a prefix of ``query`` (the
    routing-table lookup).

This is *different* from P83's character-per-edge trie: edge compression makes it
space-efficient and yields ``longest_prefix`` directly. The reported ``compression_ratio`` is
the honest one — **characters stored per node** (a plain trie stores ~1) — so it exceeds 1
whenever keys share structure. Pure stdlib; thread-safe via a single ``threading.Lock``;
deterministic.
"""

from __future__ import annotations

from typing import Any

import threading

_MISS = object()


class RadixTreeError(Exception):
    """Raised for an invalid Radix-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class _Node:
    __slots__ = ("label", "children", "is_key", "value")

    def __init__(self, label: str, is_key: bool = False, value: Any = None) -> None:
        self.label = label                      # the edge substring from this node's parent
        self.children: dict[str, _Node] = {}    # first-char of edge → child node
        self.is_key = is_key
        self.value = value


def _lcp(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


class RadixTree:
    """Path-compressed prefix tree (Patricia trie) for string keys."""

    def __init__(self, seed: int = 0) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise RadixTreeError("seed must be an int")
        self._seed = seed                       # accepted for API parity; structure is deterministic
        self._lock = threading.Lock()
        self._root = _Node("")
        self._num_keys = 0

    @staticmethod
    def _check_str(s: Any, what: str) -> str:
        if not isinstance(s, str):
            raise RadixTreeError(f"{what} must be a string")
        return s

    # ── insert ──────────────────────────────────────────────────────────────────────────
    def insert(self, key: Any, value: Any = None) -> None:
        """Insert or update ``key → value``."""
        self._check_str(key, "key")
        with self._lock:
            node = self._root
            i = 0
            while True:
                rem = key[i:]
                if rem == "":
                    if not node.is_key:
                        node.is_key = True
                        self._num_keys += 1
                    node.value = value
                    return
                c = rem[0]
                child = node.children.get(c)
                if child is None:
                    node.children[c] = _Node(rem, is_key=True, value=value)
                    self._num_keys += 1
                    return
                label = child.label
                l = _lcp(rem, label)
                if l == len(label):
                    node = child
                    i += l
                    continue
                # split the edge at the common prefix `l`
                mid = _Node(label[:l])
                child.label = label[l:]
                mid.children[child.label[0]] = child
                node.children[c] = mid
                if l == len(rem):
                    mid.is_key = True
                    mid.value = value
                else:
                    leaf = _Node(rem[l:], is_key=True, value=value)
                    mid.children[rem[l]] = leaf
                self._num_keys += 1
                return

    # ── search ──────────────────────────────────────────────────────────────────────────
    def _find(self, key: str) -> Any:
        node = self._root
        i = 0
        while True:
            rem = key[i:]
            if rem == "":
                return node.value if node.is_key else _MISS
            child = node.children.get(rem[0])
            if child is None or not rem.startswith(child.label):
                return _MISS
            node = child
            i += len(child.label)

    def search(self, key: Any) -> Any:
        """Exact lookup — the value for ``key``, or ``None`` if absent."""
        self._check_str(key, "key")
        with self._lock:
            v = self._find(key)
            return None if v is _MISS else v

    def contains(self, key: Any) -> bool:
        self._check_str(key, "key")
        with self._lock:
            return self._find(key) is not _MISS

    def __contains__(self, key: Any) -> bool:
        return self.contains(key)

    # ── delete (with re-merge) ────────────────────────────────────────────────────────────
    def delete(self, key: Any) -> bool:
        """Remove ``key``; re-merges a single-child node into its parent. Returns presence."""
        self._check_str(key, "key")
        with self._lock:
            path: list = []                     # (parent, first-char) chain to the target
            node = self._root
            i = 0
            while True:
                rem = key[i:]
                if rem == "":
                    break
                c = rem[0]
                child = node.children.get(c)
                if child is None or not rem.startswith(child.label):
                    return False
                path.append((node, c))
                node = child
                i += len(child.label)
            if not node.is_key:
                return False
            node.is_key = False
            node.value = None
            self._num_keys -= 1

            if len(node.children) == 0 and path:
                parent, c = path[-1]
                del parent.children[c]
                # parent may now be a redundant single-child non-key node → merge it up
                if len(path) >= 2 and not parent.is_key and len(parent.children) == 1:
                    gp, pc = path[-2]
                    only = next(iter(parent.children.values()))
                    only.label = parent.label + only.label
                    gp.children[pc] = only
            elif len(node.children) == 1 and not node.is_key and path:
                only = next(iter(node.children.values()))
                only.label = node.label + only.label
                parent, c = path[-1]
                parent.children[c] = only
            return True

    # ── prefix / longest-prefix ────────────────────────────────────────────────────────────
    def _collect(self, node: _Node, base: str, out: list) -> None:
        stack = [(node, base)]
        while stack:
            nd, s = stack.pop()
            if nd.is_key:
                out.append((s, nd.value))
            for child in nd.children.values():
                stack.append((child, s + child.label))

    def prefix_search(self, prefix: Any) -> list:
        """All ``(key, value)`` pairs whose key starts with ``prefix``, sorted by key."""
        self._check_str(prefix, "prefix")
        with self._lock:
            node = self._root
            i = 0
            out: list = []
            while True:
                rem = prefix[i:]
                if rem == "":
                    self._collect(node, prefix[:i], out)
                    break
                child = node.children.get(rem[0])
                if child is None:
                    break
                label = child.label
                if rem.startswith(label):
                    node = child
                    i += len(label)
                elif label.startswith(rem):     # prefix ends partway along this edge
                    self._collect(child, prefix[:i] + label, out)
                    break
                else:
                    break
            out.sort(key=lambda kv: kv[0])
            return out

    def longest_prefix(self, query: Any) -> Any:
        """The longest stored key that is a prefix of ``query``, or ``None``."""
        self._check_str(query, "query")
        with self._lock:
            node = self._root
            i = 0
            best = "" if self._root.is_key else None
            while True:
                rem = query[i:]
                if rem == "":
                    break
                child = node.children.get(rem[0])
                if child is None or not rem.startswith(child.label):
                    break
                node = child
                i += len(child.label)
                if node.is_key:
                    best = query[:i]
            return best

    def keys(self) -> list:
        """All stored keys, sorted."""
        with self._lock:
            out: list = []
            self._collect(self._root, "", out)
            return sorted(k for k, _v in out)

    def reset(self) -> None:
        """Empty the tree."""
        with self._lock:
            self._root = _Node("")
            self._num_keys = 0

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._num_keys

    @property
    def size(self) -> int:
        return self._num_keys

    @property
    def seed(self) -> int:
        return self._seed

    def _node_and_char_counts(self) -> tuple[int, int]:
        nodes = 0
        chars = 0
        stack = [self._root]
        while stack:
            nd = stack.pop()
            nodes += 1
            chars += len(nd.label)
            stack.extend(nd.children.values())
        return nodes, chars

    def num_nodes(self) -> int:
        with self._lock:
            return self._node_and_char_counts()[0]

    def stats(self) -> dict:
        """Summary: ``num_keys`` / ``num_nodes`` / ``compression_ratio`` (key chars per node)."""
        with self._lock:
            nodes, chars = self._node_and_char_counts()
            return {
                "num_keys": self._num_keys,
                "num_nodes": nodes,
                "compression_ratio": round(chars / nodes, 4) if nodes else 0.0,
                "seed": self._seed,
            }
