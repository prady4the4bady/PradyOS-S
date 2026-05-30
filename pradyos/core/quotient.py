"""Phase 90 — Sovereign Quotient Filter.

A cache-friendly approximate-membership structure (Bender et al., "Don't Thrash:
How to Cache Your Hash on Flash"). Each item is reduced to a ``q + r`` bit
fingerprint, split into a **quotient** ``fq = fp >> r`` (the *canonical slot*, in
``[0, 2**q)``) and a **remainder** ``fr = fp & (2**r − 1)`` (stored in the slot).
Collisions are resolved by linear probing, with three metadata bits per slot —
``is_occupied``, ``is_continuation``, ``is_shifted`` — that keep every quotient's
remainders in one contiguous, sorted *run*, and group overlapping runs into
*clusters*. Those bits alone drive run/cluster navigation for insert, lookup and
delete (no quotient is stored explicitly — that is the space win).

Unlike the Phase 72 Bloom filter, deletion is **exact** (no false negatives for
items that were inserted), and unlike the Phase 86 Cuckoo filter it natively
**counts duplicates** (inserting the same item twice is well-defined) and supports
**merging** two filters with the same ``q``/``r``. A membership test may still
false-*positive* with probability ``≈ 2 ** (-r)`` (two items sharing a fingerprint).

Pure stdlib. The hash is injectable (``hash_fn``) for deterministic tests.
Thread-safe via a single ``threading.Lock``; internal ``_*`` helpers run under the
lock and never re-acquire it (the lock is non-reentrant).
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any, Callable


class QuotientError(Exception):
    """Raised for an invalid quotient-filter configuration / operation. Value on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid quotient filter configuration: {detail!r}")


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class QuotientFilter:
    """Approximate-membership filter with exact delete, duplicate counting, and merge."""

    def __init__(self, q: int = 8, r: int = 8, seed: int = 0,
                 hash_fn: Callable[[Any], int] | None = None) -> None:
        if not _is_pos_int(q) or q > 32:
            raise QuotientError(q)
        if not _is_pos_int(r) or r > 32:
            raise QuotientError(r)
        if not _is_int(seed):
            raise QuotientError(seed)
        self._q = q
        self._r = r
        self._seed = seed
        self._hash_fn = hash_fn
        self._m = 1 << q                         # number of slots
        self._mask = self._m - 1
        self._fp_mask = (1 << (q + r)) - 1
        self._r_mask = (1 << r) - 1
        self._occ = bytearray(self._m)           # is_occupied
        self._cont = bytearray(self._m)          # is_continuation
        self._shift = bytearray(self._m)         # is_shifted
        self._rem = [0] * self._m                # stored remainders
        self._cnt = [0] * self._m                # per-slot duplicate counts
        self._used = 0                           # physically-occupied slots
        self._items = 0                          # total insertions (with duplicates)
        self._lock = threading.Lock()

    # ── fingerprint ───────────────────────────────────────────────────────────────
    def _fingerprint(self, item: Any) -> tuple[int, int]:
        if self._hash_fn is not None:
            h = int(self._hash_fn(item))
        else:
            data = repr((self._seed, item)).encode("utf-8")
            h = int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")
        fp = h & self._fp_mask
        return fp >> self._r, fp & self._r_mask

    # ── slot helpers (run under the lock; never re-acquire) ──────────────────────
    def _incr(self, i: int) -> int:
        return (i + 1) & self._mask

    def _decr(self, i: int) -> int:
        return (i - 1) & self._mask

    def _is_empty(self, i: int) -> bool:
        return not (self._occ[i] or self._cont[i] or self._shift[i])

    def _find_run_start(self, fq: int) -> int:
        """Slot where the run for quotient ``fq`` begins (``fq`` must be occupied)."""
        b = fq
        while self._shift[b]:
            b = self._decr(b)
        s = b
        while b != fq:
            s = self._incr(s)
            while self._cont[s]:
                s = self._incr(s)
            b = self._incr(b)
            while not self._occ[b]:
                b = self._incr(b)
        return s

    def _scan_run(self, fq: int):
        """Yield slots of ``fq``'s run in order (assumes ``fq`` occupied)."""
        s = self._find_run_start(fq)
        while True:
            yield s
            s = self._incr(s)
            if self._is_empty(s) or not self._cont[s]:
                break

    # ── insert ────────────────────────────────────────────────────────────────────
    def _insert_fp(self, fq: int, fr: int, count: int = 1) -> bool:
        # Fast path: canonical slot is completely empty.
        if self._is_empty(fq):
            self._occ[fq] = 1
            self._rem[fq] = fr
            self._cont[fq] = 0
            self._shift[fq] = 0
            self._cnt[fq] = count
            self._used += 1
            self._items += count
            return True

        new_run = not self._occ[fq]
        self._occ[fq] = 1
        run_start = self._find_run_start(fq)
        s = run_start

        if not new_run:
            # Existing run: find sorted position, or a duplicate to count.
            while True:
                if self._rem[s] == fr:
                    self._cnt[s] += count
                    self._items += count
                    return True
                if self._rem[s] > fr:
                    break
                s = self._incr(s)
                if not self._cont[s] or self._is_empty(s):
                    break

        if self._used >= self._m:
            return False                         # full — cannot place a new remainder

        new_cont = 0 if new_run else (1 if s != run_start else 0)
        force_head_continuation = (not new_run) and (s == run_start)
        self._shift_insert(fq, s, fr, new_cont, count, force_head_continuation)
        self._used += 1
        self._items += count
        return True

    def _shift_insert(self, fq: int, s: int, fr: int, cont: int, count: int,
                      force_head: bool) -> None:
        cur_rem, cur_cont, cur_cnt = fr, cont, count
        first = True
        while True:
            empty = self._is_empty(s)
            old_rem, old_cont, old_cnt = self._rem[s], self._cont[s], self._cnt[s]
            self._rem[s] = cur_rem
            self._cont[s] = cur_cont
            self._shift[s] = 0 if (first and s == fq) else 1
            self._cnt[s] = cur_cnt
            if empty:
                return
            cur_rem, cur_cnt = old_rem, old_cnt
            cur_cont = old_cont
            if first and force_head:
                cur_cont = 1                     # the old run head becomes a continuation
            first = False
            s = self._incr(s)

    # ── delete ────────────────────────────────────────────────────────────────────
    def _delete_fp(self, fq: int, fr: int) -> bool:
        if not self._occ[fq]:
            return False
        # Locate the slot holding fr within fq's run.
        s = None
        for slot in self._scan_run(fq):
            if self._rem[slot] == fr:
                s = slot
                break
            if self._rem[slot] > fr:
                return False                     # run is sorted → fr absent
        if s is None:
            return False

        if self._cnt[s] > 1:
            self._cnt[s] -= 1
            self._items -= 1
            return True

        # Remove the single entry at s, contracting the cluster.
        self._items -= 1
        self._used -= 1
        self._remove_slot(fq, s)
        return True

    def _remove_slot(self, fq: int, s: int) -> None:
        s_is_run_start = not self._cont[s]
        nxt = self._incr(s)
        run_becomes_empty = s_is_run_start and (self._is_empty(nxt) or not self._cont[nxt])

        quotient = fq
        first = True
        while True:
            curr = nxt
            if self._is_empty(curr) or not self._shift[curr]:
                # Nothing can shift into s — clear it (occupied bit is positional, untouched).
                self._rem[s] = 0
                self._cont[s] = 0
                self._shift[s] = 0
                self._cnt[s] = 0
                break
            if not self._cont[curr]:
                # curr starts a new run → it belongs to the next occupied quotient.
                quotient = self._incr(quotient)
                while not self._occ[quotient]:
                    quotient = self._incr(quotient)
            self._rem[s] = self._rem[curr]
            self._cnt[s] = self._cnt[curr]
            if first and s_is_run_start and self._cont[curr]:
                self._cont[s] = 0                # pulled continuation becomes the new run head
            else:
                self._cont[s] = self._cont[curr]
            self._shift[s] = 0 if s == quotient else 1
            first = False
            s = curr
            nxt = self._incr(curr)

        if run_becomes_empty:
            self._occ[fq] = 0

    # ── public API ────────────────────────────────────────────────────────────────
    def insert(self, item: Any) -> bool:
        """Add one occurrence of ``item``. Returns False only if the filter is full."""
        with self._lock:
            return self._insert_fp(*self._fingerprint(item))

    def contains(self, item: Any) -> bool:
        """Membership test (may false-positive, never false-negative)."""
        with self._lock:
            fq, fr = self._fingerprint(item)
            if not self._occ[fq]:
                return False
            for slot in self._scan_run(fq):
                if self._rem[slot] == fr:
                    return True
                if self._rem[slot] > fr:
                    return False
            return False

    def count(self, item: Any) -> int:
        """How many times ``item``'s fingerprint is currently stored (0 if absent)."""
        with self._lock:
            fq, fr = self._fingerprint(item)
            if not self._occ[fq]:
                return 0
            for slot in self._scan_run(fq):
                if self._rem[slot] == fr:
                    return self._cnt[slot]
                if self._rem[slot] > fr:
                    return 0
            return 0

    def delete(self, item: Any) -> bool:
        """Remove one occurrence of ``item``. Returns False if it was not present."""
        with self._lock:
            return self._delete_fp(*self._fingerprint(item))

    def _entries(self) -> list[tuple[int, int, int]]:
        """All ``(quotient, remainder, count)`` triples (under the lock)."""
        out: list[tuple[int, int, int]] = []
        for fq in range(self._m):
            if not self._occ[fq]:
                continue
            for slot in self._scan_run(fq):
                out.append((fq, self._rem[slot], self._cnt[slot]))
        return out

    def merge(self, other: "QuotientFilter") -> None:
        """Fold every entry of ``other`` (same ``q``/``r``) into this filter."""
        if not isinstance(other, QuotientFilter):
            raise QuotientError(other)
        if other._q != self._q or other._r != self._r:
            raise QuotientError((other._q, other._r))
        with other._lock:
            entries = other._entries()
        with self._lock:
            for fq, fr, count in entries:
                self._insert_fp(fq, fr, count)

    def reset(self, q: int | None = None, r: int | None = None, seed: int | None = None) -> None:
        """Clear all slots and metadata; optionally reconfigure ``q`` / ``r`` / ``seed``."""
        with self._lock:
            if q is not None:
                if not _is_pos_int(q) or q > 32:
                    raise QuotientError(q)
                self._q = q
            if r is not None:
                if not _is_pos_int(r) or r > 32:
                    raise QuotientError(r)
                self._r = r
            if seed is not None:
                if not _is_int(seed):
                    raise QuotientError(seed)
                self._seed = seed
            self._m = 1 << self._q
            self._mask = self._m - 1
            self._fp_mask = (1 << (self._q + self._r)) - 1
            self._r_mask = (1 << self._r) - 1
            self._occ = bytearray(self._m)
            self._cont = bytearray(self._m)
            self._shift = bytearray(self._m)
            self._rem = [0] * self._m
            self._cnt = [0] * self._m
            self._used = 0
            self._items = 0

    def __contains__(self, item: Any) -> bool:
        return self.contains(item)

    def __len__(self) -> int:
        with self._lock:
            return self._used

    @property
    def q(self) -> int:
        return self._q

    @property
    def remainder_bits(self) -> int:
        return self._r

    @property
    def slots(self) -> int:
        return self._m

    def stats(self) -> dict:
        """Capacity / occupancy summary, including the ``≈ 2**-r`` false-positive rate."""
        with self._lock:
            return {
                "q": self._q,
                "slots": self._m,
                "remainder_bits": self._r,
                "used": self._used,
                "items": self._items,
                "load_factor": round(self._used / self._m, 6),
                "false_positive_rate": 2.0 ** (-self._r),
            }
