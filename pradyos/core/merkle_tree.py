"""Phase 77 — Sovereign Merkle Tree (data-integrity proofs).

A Merkle tree hashes an ordered list of items into a single root hash such that
any change to any item changes the root, and membership can be proven with an
*audit path* of only ⌈log₂ n⌉ sibling hashes — without revealing the other
items. Leaves are ``SHA-256`` of each item; each level hashes adjacent pairs
(``H(left || right)``); when a level has an odd number of nodes the last node is
duplicated so the tree stays balanced.

:meth:`proof` returns the sibling hashes (with their left/right side) from a
leaf up to the root, and :meth:`verify` recomputes the root from an item plus
its proof to confirm membership. Pure stdlib (``hashlib``); thread-safe via a
single non-reentrant ``threading.Lock`` (public methods acquire it and never
call each other while holding it).
"""

from __future__ import annotations

import hashlib
import threading


class MerkleTree:
    """A SHA-256 Merkle tree with audit proofs (stdlib only)."""

    def __init__(self) -> None:
        self._leaves: list[str] = []          # leaf hashes (hex), insertion order
        self._levels: list[list[str]] = []    # level 0 = leaves … last = [root]
        self._dirty = True
        self._lock = threading.Lock()

    # ── hashing (pure; no lock) ──────────────────────────────────────────────
    @staticmethod
    def _h(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def _pair(cls, left: str, right: str) -> str:
        return cls._h(bytes.fromhex(left) + bytes.fromhex(right))

    def _leaf_hash(self, item) -> str:
        data = item.encode("utf-8") if isinstance(item, str) else repr(item).encode("utf-8")
        return self._h(data)

    # ── internal build (assumes lock held) ──────────────────────────────────
    def _build_locked(self) -> None:
        if not self._leaves:
            self._levels = []
            self._dirty = False
            return
        levels = [list(self._leaves)]
        while len(levels[-1]) > 1:
            cur = levels[-1]
            if len(cur) % 2 == 1:
                cur = cur + [cur[-1]]  # odd-leaf duplication
            levels.append([self._pair(cur[i], cur[i + 1]) for i in range(0, len(cur), 2)])
        self._levels = levels
        self._dirty = False

    def _ensure_built_locked(self) -> None:
        if self._dirty:
            self._build_locked()

    # ── mutation ──────────────────────────────────────────────────────────────
    def add(self, item) -> None:
        """Append ``item`` as a new leaf."""
        if item is None:
            raise ValueError("item must not be None")
        with self._lock:
            self._leaves.append(self._leaf_hash(item))
            self._dirty = True

    def build(self) -> str | None:
        """Force a rebuild and return the root hash (None if empty)."""
        with self._lock:
            self._build_locked()
            return self._levels[-1][0] if self._levels else None

    def clear(self) -> None:
        """Drop all leaves."""
        with self._lock:
            self._leaves = []
            self._levels = []
            self._dirty = True

    # ── queries ─────────────────────────────────────────────────────────────
    @property
    def root(self) -> str | None:
        """Current root hash (hex), or None when the tree is empty."""
        with self._lock:
            self._ensure_built_locked()
            return self._levels[-1][0] if self._levels else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._leaves)

    def proof(self, item) -> list[dict]:
        """Audit path for ``item``: sibling hashes from leaf to root.

        Each entry is ``{"hash": <hex>, "side": "left"|"right"}`` giving the
        sibling's value and which side it sits on. Raises :class:`ValueError`
        if the tree is empty or ``item`` is not a leaf.
        """
        if item is None:
            raise ValueError("item must not be None")
        with self._lock:
            self._ensure_built_locked()
            if not self._levels:
                raise ValueError("cannot prove membership in an empty tree")
            leaf = self._leaf_hash(item)
            try:
                idx = self._leaves.index(leaf)
            except ValueError:
                raise ValueError("item is not in the tree") from None
            path: list[dict] = []
            for level in self._levels[:-1]:        # every level except the root
                nodes = level if len(level) % 2 == 0 else level + [level[-1]]
                if idx % 2 == 0:
                    path.append({"hash": nodes[idx + 1], "side": "right"})
                else:
                    path.append({"hash": nodes[idx - 1], "side": "left"})
                idx //= 2
            return path

    def verify(self, item) -> bool:
        """True if ``item`` is a leaf whose audit path recomputes the root."""
        if item is None:
            return False
        current_root = self.root
        if current_root is None:
            return False
        leaf = self._leaf_hash(item)
        try:
            path = self.proof(item)
        except ValueError:
            return False
        computed = leaf
        for step in path:
            if step["side"] == "left":
                computed = self._pair(step["hash"], computed)
            else:
                computed = self._pair(computed, step["hash"])
        return computed == current_root

    def stats(self) -> dict:
        """JSON-serialisable snapshot: leaf count, tree height, and root."""
        with self._lock:
            self._ensure_built_locked()
            return {
                "leaves": len(self._leaves),
                "height": (len(self._levels) - 1) if self._levels else 0,
                "root": self._levels[-1][0] if self._levels else None,
            }
