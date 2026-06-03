"""Phase 150 — Sovereign Pairing Heap (Fredman–Sedgewick–Sleator–Tarjan, 1986).

A **self-adjusting mergeable min-priority-queue** whose distinguishing feature is
**`decrease_key` in `O(log n)` amortized** (with `O(1)` `insert`, `find_min`, and internal `meld`)
— a capability the platform's other heaps lack: the Skew Heap (P136) melds but exposes no
key-decrease, and the Min-Max Heap (P144) is double-ended but neither melds nor decreases keys.

The heap is a single **multiway tree kept min-at-root**. `insert` melds in a one-node tree;
`delete_min` removes the root and re-pairs its children with the classic **two-pass** merge
(left→right meld consecutive pairs, then right→left accumulate); `decrease_key` lowers a node's
value, detaches its subtree, and melds it back at the root. Nodes live in append-only parallel
arrays (`_val` / `_child` / `_sibling` / `_parent`) indexed by a **stable integer handle**
returned from `insert`, which is what makes `decrease_key` addressable. Every child of a node `x`
has `_parent == x`, and a node's children form a singly-linked `_sibling` list.

All operations are iterative (two-pass loop, sibling-walk detach, `O(1)` meld). Pure stdlib;
thread-safe via a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

from typing import Any

import threading

_NULL = -1


class PairingHeapError(Exception):
    """Raised for an invalid pairing-heap operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class PairingHeap:
    """Mergeable min-PQ with O(log n) amortized decrease_key; handles are stable ints."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clear()

    def _clear(self) -> None:
        self._val: list[float] = []
        self._child: list[int] = []
        self._sibling: list[int] = []
        self._parent: list[int] = []
        self._alive: list[bool] = []
        self._root = _NULL
        self._size = 0

    def _new_node(self, value: float) -> int:
        self._val.append(value)
        self._child.append(_NULL)
        self._sibling.append(_NULL)
        self._parent.append(_NULL)
        self._alive.append(True)
        return len(self._val) - 1

    def _meld(self, a: int, b: int) -> int:
        """Meld two roots; the smaller value (ties → ``a``) becomes the parent. Returns new root."""
        if a == _NULL:
            return b
        if b == _NULL:
            return a
        if self._val[a] <= self._val[b]:
            self._sibling[b] = self._child[a]
            self._parent[b] = a
            self._child[a] = b
            return a
        self._sibling[a] = self._child[b]
        self._parent[a] = b
        self._child[b] = a
        return b

    # ── insert ───────────────────────────────────────────────────────────────────────────
    def insert(self, value: float) -> int:
        """Insert ``value``; return a stable handle for later ``decrease_key``."""
        if not _is_num(value):
            raise PairingHeapError("value must be a number")
        with self._lock:
            h = self._new_node(value)
            self._root = self._meld(self._root, h)
            self._parent[self._root] = _NULL
            self._size += 1
            return h

    # ── find_min ─────────────────────────────────────────────────────────────────────────
    def find_min(self) -> float:
        """Smallest value in the heap (raises if empty)."""
        with self._lock:
            if self._root == _NULL:
                raise PairingHeapError("heap is empty")
            return self._val[self._root]

    def find_min_handle(self) -> int:
        """Handle of the current minimum (raises if empty)."""
        with self._lock:
            if self._root == _NULL:
                raise PairingHeapError("heap is empty")
            return self._root

    # ── delete_min (two-pass pairing) ─────────────────────────────────────────────────────
    def delete_min(self) -> float:
        """Remove and return the smallest value (raises if empty)."""
        with self._lock:
            r = self._root
            if r == _NULL:
                raise PairingHeapError("heap is empty")
            # collect children of the root, detaching each
            children = []
            c = self._child[r]
            while c != _NULL:
                nxt = self._sibling[c]
                self._sibling[c] = _NULL
                self._parent[c] = _NULL
                children.append(c)
                c = nxt
            # pass 1: left→right meld consecutive pairs
            merged = []
            i = 0
            m = len(children)
            while i < m:
                if i + 1 < m:
                    merged.append(self._meld(children[i], children[i + 1]))
                    i += 2
                else:
                    merged.append(children[i])
                    i += 1
            # pass 2: right→left accumulate
            new_root = _NULL
            if merged:
                acc = merged[-1]
                for j in range(len(merged) - 2, -1, -1):
                    acc = self._meld(merged[j], acc)
                new_root = acc
            value = self._val[r]
            self._alive[r] = False
            self._child[r] = _NULL
            self._root = new_root
            if new_root != _NULL:
                self._parent[new_root] = _NULL
            self._size -= 1
            return value

    # ── decrease_key ───────────────────────────────────────────────────────────────────────
    def decrease_key(self, handle: int, value: float) -> None:
        """Lower the value at ``handle`` to ``value`` (must not increase it)."""
        if not _is_int(handle):
            raise PairingHeapError("handle must be an int")
        if not _is_num(value):
            raise PairingHeapError("value must be a number")
        with self._lock:
            if not (0 <= handle < len(self._val)) or not self._alive[handle]:
                raise PairingHeapError("handle is not a live element")
            if value > self._val[handle]:
                raise PairingHeapError("decrease_key cannot increase the value")
            self._val[handle] = value
            if handle == self._root:
                return
            # detach handle's subtree from its parent's child list
            p = self._parent[handle]
            if self._child[p] == handle:
                self._child[p] = self._sibling[handle]
            else:
                s = self._child[p]
                while self._sibling[s] != handle:
                    s = self._sibling[s]
                self._sibling[s] = self._sibling[handle]
            self._parent[handle] = _NULL
            self._sibling[handle] = _NULL
            self._root = self._meld(self._root, handle)
            self._parent[self._root] = _NULL

    # ── maintenance / introspection ──────────────────────────────────────────────────────
    def reset(self) -> None:
        """Discard all elements."""
        with self._lock:
            self._clear()

    def is_empty(self) -> bool:
        with self._lock:
            return self._size == 0

    def __len__(self) -> int:
        return self._size

    @property
    def size(self) -> int:
        return self._size

    def stats(self) -> dict:
        """Summary: ``size`` / ``nodes`` (handles allocated) / ``min`` (None if empty)."""
        with self._lock:
            return {"size": self._size, "nodes": len(self._val),
                    "min": None if self._root == _NULL else self._val[self._root]}
