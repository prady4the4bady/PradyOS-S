"""Phase 141 — Sovereign Suffix Array (Manber & Myers, 1990).

A **sorted index of all suffixes of a string** that answers substring queries by binary
search — a new text-indexing capability that pairs with the Wavelet Tree (P135) and Radix
Tree (P140). The array stores the starting positions of every suffix of the text in
lexicographic order. Because all occurrences of a pattern ``p`` are exactly the suffixes whose
prefix is ``p``, and the suffixes are sorted, those occurrences form a **contiguous block** —
found with two binary searches (lower/upper bound). So ``contains`` / ``count`` /
``positions`` run in ``O(m log n)`` for a length-``m`` pattern.

An accompanying **LCP** (longest-common-prefix) array records, for each adjacent pair in
sorted order, the length of their shared prefix — from which the number of **distinct
substrings** of the text falls out as ``n(n+1)/2 − Σ LCP``.

This is *different* from the platform's prefix trees: a suffix array indexes *every substring*
of one text — the backbone of full-text search and bioinformatics. The build sorts the
suffixes directly (unambiguously correct); queries are pure binary search. Pure stdlib;
thread-safe via a single ``threading.Lock``; deterministic (static — built once from the text).
"""

from __future__ import annotations

import threading
from typing import Any


class SuffixArrayError(Exception):
    """Raised for an invalid Suffix-array operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class SuffixArray:
    """Sorted suffix index with O(m log n) substring search + LCP array."""

    def __init__(self, text: str = "") -> None:
        self._lock = threading.Lock()
        self._build(text)

    # ── build ──────────────────────────────────────────────────────────────────────────
    def _build_locked(self, text: Any) -> None:
        if not isinstance(text, str):
            raise SuffixArrayError("text must be a string")
        self._text = text
        n = len(text)
        self._n = n
        # Sort suffix start positions by the suffix string (unambiguously correct).
        self._sa = sorted(range(n), key=lambda i: text[i:])

    def _build(self, text: Any) -> None:
        with self._lock:
            self._build_locked(text)

    def build(self, text: Any) -> None:
        """(Re)build the index from ``text`` (static — replaces any prior contents)."""
        with self._lock:
            self._build_locked(text)

    # ── substring search (binary bounds over the suffix array) ────────────────────────
    def _prefix(self, start: int, m: int) -> str:
        return self._text[start:start + m]

    def _lower(self, p: str) -> int:
        """Leftmost SA index whose suffix prefix (truncated to len(p)) is ``>= p``."""
        lo, hi, m = 0, self._n, len(p)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._prefix(self._sa[mid], m) < p:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _upper(self, p: str) -> int:
        """Leftmost SA index whose suffix prefix (truncated to len(p)) is ``> p``."""
        lo, hi, m = 0, self._n, len(p)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._prefix(self._sa[mid], m) <= p:
                lo = mid + 1
            else:
                hi = mid
        return lo

    @staticmethod
    def _check_pattern(pattern: Any) -> str:
        if not isinstance(pattern, str):
            raise SuffixArrayError("pattern must be a string")
        if pattern == "":
            raise SuffixArrayError("pattern must be non-empty")
        return pattern

    def contains(self, pattern: Any) -> bool:
        """Whether ``pattern`` occurs in the text."""
        self._check_pattern(pattern)
        with self._lock:
            return self._upper(pattern) - self._lower(pattern) > 0

    def count(self, pattern: Any) -> int:
        """Number of (possibly overlapping) occurrences of ``pattern`` in the text."""
        self._check_pattern(pattern)
        with self._lock:
            return self._upper(pattern) - self._lower(pattern)

    def positions(self, pattern: Any) -> list:
        """Sorted start positions of every occurrence of ``pattern``."""
        self._check_pattern(pattern)
        with self._lock:
            return sorted(self._sa[self._lower(pattern):self._upper(pattern)])

    # ── arrays ──────────────────────────────────────────────────────────────────────────
    def suffix_array(self) -> list:
        """A copy of the suffix array (suffix start positions in lexicographic order)."""
        with self._lock:
            return list(self._sa)

    def _lcp_len(self, i: int, j: int) -> int:
        text, n = self._text, self._n
        k = 0
        while i + k < n and j + k < n and text[i + k] == text[j + k]:
            k += 1
        return k

    def _lcp_locked(self) -> list:
        lcp = [0] * self._n
        for r in range(1, self._n):
            lcp[r] = self._lcp_len(self._sa[r - 1], self._sa[r])
        return lcp

    def lcp_array(self) -> list:
        """LCP array: ``lcp[r]`` = common-prefix length of the suffixes at SA[r-1] and SA[r]
        (``lcp[0] = 0``)."""
        with self._lock:
            return self._lcp_locked()

    def reset(self) -> None:
        """Empty the index."""
        with self._lock:
            self._build_locked("")

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._n

    @property
    def size(self) -> int:
        return self._n

    @property
    def text(self) -> str:
        return self._text

    def distinct_substrings(self) -> int:
        """Number of distinct non-empty substrings = ``n(n+1)/2 − Σ LCP``."""
        with self._lock:
            return self._n * (self._n + 1) // 2 - sum(self._lcp_locked())

    def stats(self) -> dict:
        """Summary: ``size`` / ``num_suffixes`` / ``distinct_substrings``."""
        with self._lock:
            distinct = self._n * (self._n + 1) // 2 - sum(self._lcp_locked())
            return {"size": self._n, "num_suffixes": self._n, "distinct_substrings": distinct}
