"""Phase 151 — Sovereign Suffix Automaton (Blumer et al. 1985 / Crochemore).

The **minimal deterministic finite automaton that recognizes exactly the substrings** of a
string, built **online** in `O(n)` amortized (for a constant-ish alphabet) by appending one
character at a time and splitting/cloning states along *suffix links*. Paths from the initial
state spell precisely the substrings of the text, so membership is an `O(|p|)` walk, and the
**number of distinct substrings** is `Σ (len[v] − len[link[v]])` over every non-initial state.

This is the platform's *first* automaton-of-all-substrings — distinct from the sorted-suffix
index (Suffix Array/P141, which answers substring queries by binary search over sorted suffixes)
and the multi-pattern failure-link trie (Aho–Corasick/P142, which scans for a *fixed* dictionary).

States live in parallel lists: ``_len`` (longest string in a state's end-position class),
``_link`` (suffix link), and ``_trans`` (a list of ``char -> state`` dicts, so the alphabet may be
arbitrary — ASCII or Unicode). State ``0`` is the initial state (``len 0``, ``link -1``). The
online ``extend`` uses only ``while`` loops — there is no recursion. Pure stdlib; thread-safe via
a single ``threading.Lock``; deterministic.
"""

from __future__ import annotations

from typing import Any

import threading


class SuffixAutomatonError(Exception):
    """Raised for an invalid suffix-automaton operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class SuffixAutomaton:
    """Minimal automaton of all substrings; online build, O(|p|) membership, distinct-substring count."""

    def __init__(self, text: Any = None) -> None:
        self._lock = threading.Lock()
        self._init_state()
        if text is not None:
            self.build(text)

    def _init_state(self) -> None:
        # state 0 is the initial state
        self._len = [0]
        self._link = [-1]
        self._trans: list[dict] = [{}]
        self._last = 0
        self._length = 0          # number of characters added (length of the text)

    def _new_state(self, length: int, link: int, trans: dict) -> int:
        self._len.append(length)
        self._link.append(link)
        self._trans.append(trans)
        return len(self._len) - 1

    # ── online construction ───────────────────────────────────────────────────────────────
    def _extend_locked(self, ch: str) -> None:
        cur = self._new_state(self._len[self._last] + 1, -1, {})
        p = self._last
        while p != -1 and ch not in self._trans[p]:
            self._trans[p][ch] = cur
            p = self._link[p]
        if p == -1:
            self._link[cur] = 0
        else:
            q = self._trans[p][ch]
            if self._len[p] + 1 == self._len[q]:
                self._link[cur] = q
            else:
                clone = self._new_state(self._len[p] + 1, self._link[q], dict(self._trans[q]))
                while p != -1 and self._trans[p].get(ch) == q:
                    self._trans[p][ch] = clone
                    p = self._link[p]
                self._link[q] = clone
                self._link[cur] = clone
        self._last = cur
        self._length += 1

    def extend(self, ch: Any) -> None:
        """Append a single character to the automaton."""
        if not isinstance(ch, str) or len(ch) != 1:
            raise SuffixAutomatonError("extend expects a single-character string")
        with self._lock:
            self._extend_locked(ch)

    def build(self, text: Any) -> None:
        """(Re)build the automaton from ``text`` (replaces any prior contents)."""
        if not isinstance(text, str):
            raise SuffixAutomatonError("text must be a string")
        with self._lock:
            self._init_state()
            for ch in text:
                self._extend_locked(ch)

    # ── queries ──────────────────────────────────────────────────────────────────────────
    def contains(self, pattern: Any) -> bool:
        """True iff ``pattern`` is a substring of the built text (empty string → True)."""
        if not isinstance(pattern, str):
            raise SuffixAutomatonError("pattern must be a string")
        with self._lock:
            cur = 0
            for ch in pattern:
                nxt = self._trans[cur].get(ch)
                if nxt is None:
                    return False
                cur = nxt
            return True

    def distinct_substrings(self) -> int:
        """Number of distinct non-empty substrings of the text."""
        with self._lock:
            total = 0
            for v in range(1, len(self._len)):
                total += self._len[v] - self._len[self._link[v]]
            return total

    def reset(self) -> None:
        """Clear the automaton back to the empty string."""
        with self._lock:
            self._init_state()

    # ── introspection ──────────────────────────────────────────────────────────────────────
    @property
    def num_states(self) -> int:
        return len(self._len)

    @property
    def length(self) -> int:
        return self._length

    def __len__(self) -> int:
        return self._length

    def stats(self) -> dict:
        """Summary: ``num_states`` / ``length`` / ``distinct_substrings`` / ``transitions``."""
        with self._lock:
            distinct = 0
            for v in range(1, len(self._len)):
                distinct += self._len[v] - self._len[self._link[v]]
            transitions = sum(len(t) for t in self._trans)
            return {"num_states": len(self._len), "length": self._length,
                    "distinct_substrings": distinct, "transitions": transitions}
