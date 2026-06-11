"""Phase 135 — Sovereign Wavelet Tree (Grossi, Gupta & Vitter, 2003).

A **succinct index over an arbitrary-alphabet sequence** that lifts rank/select from *bits*
to *symbols* — built directly on the Rank/Select primitive of P134. A new capability for the
platform: where ``RankSelect`` answers rank/select on a bit array, a wavelet tree answers them
on a sequence over any ordered alphabet, plus order-statistic queries.

Construction. Distinct symbols are mapped to contiguous ids ``[0, σ)`` in sorted order. The
root holds a bitvector marking, per position, whether that symbol's id falls in the **lower**
half ``[lo, mid)`` (bit 0) or **upper** half ``[mid, hi)`` (bit 1) of the alphabet range;
positions then recurse into a left child (lower half) and a right child (upper half),
``⌈log₂ σ⌉`` levels deep. Each node's bitvector is a :class:`RankSelect`.

With `rank`/`select` on each level, the tree answers in ``O(log σ)``:

  * ``access(i)`` — the symbol at position ``i``;
  * ``rank(symbol, i)`` — occurrences of ``symbol`` in ``[0, i)``;
  * ``select(symbol, k)`` — position of the ``k``-th ``symbol`` (1-indexed);
  * ``quantile(i, j, k)`` — the ``k``-th smallest symbol in range ``[i, j)``;
  * ``range_count(i, j, lo, hi)`` — symbols in ``[i, j)`` with value in ``[lo, hi)``.

This is *exact* (distinct from the platform's approximate frequency sketches) and is the
backbone of compressed text indexes. Pure stdlib (reusing :class:`RankSelect`); thread-safe
via a single ``threading.Lock``; deterministic (static — built once from the sequence).
"""

from __future__ import annotations

import bisect
import threading
from collections.abc import Iterable
from typing import Any

from pradyos.core.rank_select import RankSelect


class WaveletTreeError(Exception):
    """Raised for an invalid Wavelet-tree operation / input. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


class _Node:
    __slots__ = ("lo", "hi", "bitvector", "left", "right")

    def __init__(self, lo: int, hi: int) -> None:
        self.lo = lo  # alphabet id range [lo, hi)
        self.hi = hi
        self.bitvector: RankSelect | None = None
        self.left: _Node | None = None
        self.right: _Node | None = None


def _kind(symbol: Any) -> str:
    if isinstance(symbol, bool):
        raise WaveletTreeError("symbol must be int, float or str (not bool)")
    if isinstance(symbol, int | float):
        return "num"
    if isinstance(symbol, str):
        return "str"
    raise WaveletTreeError("symbol must be int, float or str")


class WaveletTree:
    """Succinct sequence index (access / rank / select / quantile / range-count)."""

    def __init__(self, sequence: Any = None) -> None:
        self._lock = threading.Lock()
        self._build([] if sequence is None else sequence)

    # ── build ──────────────────────────────────────────────────────────────────────────
    def _build_locked(self, sequence: Iterable[Any]) -> None:
        try:
            seq = list(sequence)
        except TypeError as exc:
            raise WaveletTreeError("sequence must be iterable") from exc

        kind: str | None = None
        for s in seq:
            k = _kind(s)  # validates type (raises on bool/non-orderable)
            if kind is None:
                kind = k
            elif k != kind:
                raise WaveletTreeError(f"mixed symbol kinds {kind!r} and {k!r}")

        symbols = sorted(set(seq))  # id i ↔ symbols[i], ascending
        sym2id = {s: i for i, s in enumerate(symbols)}
        ids = [sym2id[s] for s in seq]
        sigma = len(symbols)

        self._n = len(seq)
        self._kind = kind
        self._symbols = symbols
        self._sym2id = sym2id
        self._sigma = sigma
        self._root = self._make(ids, 0, sigma) if sigma > 0 else None

    def _make(self, ids: list, lo: int, hi: int) -> _Node:
        node = _Node(lo, hi)
        if hi - lo <= 1:  # leaf — covers the single id `lo`
            return node
        mid = (lo + hi) // 2
        bits = [0 if x < mid else 1 for x in ids]
        node.bitvector = RankSelect(bits)
        node.left = self._make([x for x in ids if x < mid], lo, mid)
        node.right = self._make([x for x in ids if x >= mid], mid, hi)
        return node

    def _build(self, sequence: Iterable[Any]) -> None:
        with self._lock:
            self._build_locked(sequence)

    def build(self, sequence: Iterable[Any]) -> None:
        """(Re)build the index from ``sequence`` (static — replaces any prior contents)."""
        with self._lock:
            self._build_locked(sequence)

    # ── helpers (called under the lock) ──────────────────────────────────────────────
    def _check_index(self, i: int, lo: int, hi: int, name: str) -> None:
        if not isinstance(i, int) or isinstance(i, bool) or not (lo <= i <= hi):
            raise WaveletTreeError(f"{name} must be an int in [{lo}, {hi}]")

    def _access_locked(self, i: int) -> int:
        node = self._root
        while node.left is not None:
            if node.bitvector.get(i) == 0:
                i = node.bitvector.rank0(i)
                node = node.left
            else:
                i = node.bitvector.rank1(i)
                node = node.right
        return node.lo  # leaf id

    def _rank_id_locked(self, sym_id: int, i: int) -> int:
        node = self._root
        while node.left is not None:
            mid = (node.lo + node.hi) // 2
            if sym_id < mid:
                i = node.bitvector.rank0(i)
                node = node.left
            else:
                i = node.bitvector.rank1(i)
                node = node.right
        return i  # count of sym_id in [0, original_i)

    def _count_less(self, node: _Node, i: int, j: int, x: int) -> int:
        """Positions in ``[i, j)`` at ``node`` whose id is ``< x``."""
        if i >= j or x <= node.lo:
            return 0
        if x >= node.hi:
            return j - i
        bv = node.bitvector  # not a leaf here (lo < x < hi ⇒ hi-lo ≥ 2)
        z_i, z_j = bv.rank0(i), bv.rank0(j)
        mid = (node.lo + node.hi) // 2
        if x <= mid:
            return self._count_less(node.left, z_i, z_j, x)
        return (z_j - z_i) + self._count_less(node.right, i - z_i, j - z_j, x)

    # ── queries ──────────────────────────────────────────────────────────────────────
    def access(self, i: int) -> Any:
        """The symbol at position ``i`` (``i`` in ``[0, n)``)."""
        with self._lock:
            self._check_index(i, 0, self._n - 1, "i")
            return self._symbols[self._access_locked(i)]

    def rank(self, symbol: Any, i: int) -> int:
        """Occurrences of ``symbol`` in ``[0, i)`` (``i`` in ``[0, n]``)."""
        _kind(symbol)  # validates type
        with self._lock:
            self._check_index(i, 0, self._n, "i")
            sym_id = self._sym2id.get(symbol)
            if sym_id is None or i == 0:
                return 0
            return self._rank_id_locked(sym_id, i)

    def select(self, symbol: Any, k: int) -> int:
        """Position of the ``k``-th ``symbol`` (1-indexed); raises if fewer than ``k`` exist."""
        _kind(symbol)
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise WaveletTreeError("k must be an int >= 1")
        with self._lock:
            sym_id = self._sym2id.get(symbol)
            if sym_id is None or k > self._rank_id_locked(sym_id, self._n):
                raise WaveletTreeError(f"fewer than {k} occurrences of {symbol!r}")
            # descend to the leaf for sym_id, recording the path
            path = []
            node = self._root
            while node.left is not None:
                mid = (node.lo + node.hi) // 2
                if sym_id < mid:
                    path.append((node, False))
                    node = node.left
                else:
                    path.append((node, True))
                    node = node.right
            pos = k - 1  # 0-indexed within the leaf
            for parent, went_right in reversed(path):
                bv = parent.bitvector
                pos = bv.select1(pos + 1) if went_right else bv.select0(pos + 1)
            return pos

    def quantile(self, i: int, j: int, k: int) -> Any:
        """The ``k``-th smallest symbol (1-indexed) in range ``[i, j)``."""
        with self._lock:
            if (
                not isinstance(i, int)
                or isinstance(i, bool)
                or not isinstance(j, int)
                or isinstance(j, bool)
                or not (0 <= i < j <= self._n)
            ):
                raise WaveletTreeError(f"need 0 <= i < j <= {self._n}")
            if not isinstance(k, int) or isinstance(k, bool) or not (1 <= k <= j - i):
                raise WaveletTreeError(f"k must be an int in [1, {j - i}]")
            node = self._root
            while node.left is not None:
                bv = node.bitvector
                z_i, z_j = bv.rank0(i), bv.rank0(j)
                zeros = z_j - z_i
                if k <= zeros:
                    i, j, node = z_i, z_j, node.left
                else:
                    k -= zeros
                    i, j, node = i - z_i, j - z_j, node.right
            return self._symbols[node.lo]

    def range_count(self, i: int, j: int, lo: Any, hi: Any) -> int:
        """Count of positions in ``[i, j)`` whose symbol is in ``[lo, hi)`` (``hi`` exclusive)."""
        klo, khi = _kind(lo), _kind(hi)
        with self._lock:
            if (
                not isinstance(i, int)
                or isinstance(i, bool)
                or not isinstance(j, int)
                or isinstance(j, bool)
                or not (0 <= i <= j <= self._n)
            ):
                raise WaveletTreeError(f"need 0 <= i <= j <= {self._n}")
            if self._kind is not None and (klo != self._kind or khi != self._kind):
                raise WaveletTreeError("bound kind does not match symbol kind")
            if self._root is None or i == j or lo >= hi:
                return 0
            lo_id = bisect.bisect_left(self._symbols, lo)  # first id with symbol >= lo
            hi_id = bisect.bisect_left(self._symbols, hi)  # first id with symbol >= hi
            if lo_id >= hi_id:
                return 0
            return self._count_less(self._root, i, j, hi_id) - self._count_less(
                self._root, i, j, lo_id
            )

    def reset(self) -> None:
        """Empty the index."""
        with self._lock:
            self._build_locked([])

    # ── introspection ──────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._n

    @property
    def size(self) -> int:
        return self._n

    @property
    def alphabet_size(self) -> int:
        return self._sigma

    @property
    def symbols(self) -> list:
        return list(self._symbols)

    def _height(self) -> int:
        return (self._sigma - 1).bit_length() if self._sigma > 1 else (1 if self._sigma == 1 else 0)

    def stats(self) -> dict:
        """Summary: ``size`` / ``alphabet_size`` / ``height`` / ``kind``."""
        with self._lock:
            return {
                "size": self._n,
                "alphabet_size": self._sigma,
                "height": self._height(),
                "kind": self._kind,
            }
