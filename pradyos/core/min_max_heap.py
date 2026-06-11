"""Phase 144 — Sovereign Min-Max Heap (Atkinson, Sack, Santoro & Strothotte, 1986).

A **double-ended priority queue** — `O(1)` access to *both* the minimum and the maximum, and
`O(log n)` `extract_min` / `extract_max` — a new capability for the platform (the Skew Heap of
P136 is a min-only meldable queue). It is a single array-backed binary heap whose levels
**alternate**: a node on an even (min) level is `≤` all its descendants; a node on an odd (max)
level is `≥` all its descendants.

Insertion appends and **bubbles up against grandparents** on the matching level type.
`extract_min` removes the root and `extract_max` removes the larger of the root's children;
both **sift down** by repeatedly swapping with the smallest/largest among a node's children
*and grandchildren* (the grandchild step, with a possible parent fix-up, is what keeps both
ends cheap simultaneously).

Supports `push` / `push_many`, `peek_min` / `peek_max`, `extract_min` / `extract_max`,
`keys_sorted`, and `__len__`. Values must be one orderable kind (`int`/`float` or `str`). Pure
stdlib; thread-safe via a single ``threading.Lock``; deterministic; sift-down is iterative.
"""

from __future__ import annotations

import threading
from typing import Any


class MinMaxHeapError(Exception):
    """Raised for an invalid Min-Max-heap operation. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        raise MinMaxHeapError("value must be int, float or str (not bool)")
    if isinstance(value, int | float):
        return "num"
    if isinstance(value, str):
        return "str"
    raise MinMaxHeapError("value must be int, float or str")


def _is_min_level(i: int) -> bool:
    return ((i + 1).bit_length() - 1) % 2 == 0  # level = floor(log2(i+1)); even ⇒ min level


class MinMaxHeap:
    """Array-backed double-ended priority queue (alternating min/max levels)."""

    def __init__(self) -> None:
        self._a: list = []
        self._kind: str | None = None  # 'num' or 'str' — values must be mutually orderable
        self._lock = threading.Lock()

    # ── push (bubble up against grandparents) ────────────────────────────────────────
    def _bubble_up_min(self, i: int) -> None:
        a = self._a
        while i >= 3:
            gp = ((i - 1) // 2 - 1) // 2
            if a[i] < a[gp]:
                a[i], a[gp] = a[gp], a[i]
                i = gp
            else:
                break

    def _bubble_up_max(self, i: int) -> None:
        a = self._a
        while i >= 3:
            gp = ((i - 1) // 2 - 1) // 2
            if a[i] > a[gp]:
                a[i], a[gp] = a[gp], a[i]
                i = gp
            else:
                break

    def _bubble_up(self, i: int) -> None:
        if i == 0:
            return
        a = self._a
        p = (i - 1) // 2
        if _is_min_level(i):
            if a[i] > a[p]:
                a[i], a[p] = a[p], a[i]
                self._bubble_up_max(p)
            else:
                self._bubble_up_min(i)
        else:
            if a[i] < a[p]:
                a[i], a[p] = a[p], a[i]
                self._bubble_up_min(p)
            else:
                self._bubble_up_max(i)

    def push(self, value: Any) -> None:
        """Insert ``value`` (duplicates allowed)."""
        kind = _kind(value)
        with self._lock:
            if self._kind is None:
                self._kind = kind
            elif kind != self._kind:
                raise MinMaxHeapError(
                    f"value kind {kind!r} does not match heap kind {self._kind!r}"
                )
            self._a.append(value)
            self._bubble_up(len(self._a) - 1)

    def push_many(self, values: Any) -> int:
        """Push many values; returns the number consumed."""
        try:
            items = list(values)
        except TypeError as exc:
            raise MinMaxHeapError("values must be iterable") from exc
        for v in items:
            self.push(v)
        return len(items)

    # ── sift down (children + grandchildren) ──────────────────────────────────────────
    def _descendants(self, i: int, n: int) -> list:
        out = []
        for c in (2 * i + 1, 2 * i + 2):
            if c < n:
                out.append(c)
                for g in (2 * c + 1, 2 * c + 2):
                    if g < n:
                        out.append(g)
        return out

    def _trickle_down_min(self, i: int) -> None:
        a = self._a
        n = len(a)
        while True:
            desc = self._descendants(i, n)
            if not desc:
                return
            m = min(desc, key=lambda j: a[j])
            if a[m] >= a[i]:
                return
            a[m], a[i] = a[i], a[m]
            if m > 2 * i + 2:  # m is a grandchild → fix its parent, keep going
                p = (m - 1) // 2
                if a[m] > a[p]:
                    a[m], a[p] = a[p], a[m]
                i = m
            else:  # m is a direct child → done
                return

    def _trickle_down_max(self, i: int) -> None:
        a = self._a
        n = len(a)
        while True:
            desc = self._descendants(i, n)
            if not desc:
                return
            m = max(desc, key=lambda j: a[j])
            if a[m] <= a[i]:
                return
            a[m], a[i] = a[i], a[m]
            if m > 2 * i + 2:
                p = (m - 1) // 2
                if a[m] < a[p]:
                    a[m], a[p] = a[p], a[m]
                i = m
            else:
                return

    def _trickle_down(self, i: int) -> None:
        if _is_min_level(i):
            self._trickle_down_min(i)
        else:
            self._trickle_down_max(i)

    # ── peek / extract ────────────────────────────────────────────────────────────────
    def peek_min(self) -> Any:
        """The minimum value (root); raises if empty."""
        with self._lock:
            if not self._a:
                raise MinMaxHeapError("peek_min on an empty heap")
            return self._a[0]

    def _max_index(self) -> int:
        a = self._a
        if len(a) == 1:
            return 0
        if len(a) == 2:
            return 1
        return 1 if a[1] >= a[2] else 2

    def peek_max(self) -> Any:
        """The maximum value (the larger of the root's children); raises if empty."""
        with self._lock:
            if not self._a:
                raise MinMaxHeapError("peek_max on an empty heap")
            return self._a[self._max_index()]

    def extract_min(self) -> Any:
        """Remove and return the minimum; raises if empty."""
        with self._lock:
            a = self._a
            if not a:
                raise MinMaxHeapError("extract_min on an empty heap")
            if len(a) == 1:
                v = a.pop()
                self._kind = None
                return v
            v = a[0]
            a[0] = a.pop()
            self._trickle_down_min(0)
            return v

    def extract_max(self) -> Any:
        """Remove and return the maximum; raises if empty."""
        with self._lock:
            a = self._a
            if not a:
                raise MinMaxHeapError("extract_max on an empty heap")
            mi = self._max_index()
            if mi == len(a) - 1:  # max is the last slot → just pop
                v = a.pop()
            else:
                v = a[mi]
                a[mi] = a.pop()
                self._trickle_down(mi)
            if not a:
                self._kind = None
            return v

    def reset(self) -> None:
        """Empty the heap."""
        with self._lock:
            self._a = []
            self._kind = None

    # ── introspection ──────────────────────────────────────────────────────────────────
    def keys_sorted(self) -> list:
        """All values in ascending order (read-only)."""
        with self._lock:
            return sorted(self._a)

    def is_empty(self) -> bool:
        return len(self._a) == 0

    def __len__(self) -> int:
        return len(self._a)

    @property
    def size(self) -> int:
        return len(self._a)

    @property
    def kind(self) -> str | None:
        return self._kind

    def stats(self) -> dict:
        """Summary: ``size`` / ``min`` / ``max`` (``None`` if empty) / ``kind``."""
        with self._lock:
            if not self._a:
                return {"size": 0, "min": None, "max": None, "kind": self._kind}
            return {
                "size": len(self._a),
                "min": self._a[0],
                "max": self._a[self._max_index()],
                "kind": self._kind,
            }
