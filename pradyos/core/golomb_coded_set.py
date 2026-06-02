"""Phase 128 — Sovereign Golomb-Coded Set (Putze, Sanders & Singler, 2007; Golomb–Rice, 1966).

A **compressed, space-optimal static set-membership** structure — a new capability for the
platform. Where the Bloom family (P72 / counting / scalable / stable / cuckoo / xor /
binary-fuse / ribbon / quotient) keeps membership in a *live bit-array*, a Golomb-Coded Set
(GCS) stores the set as a *compressed byte stream* and is queried by decoding:

  1. Hash the ``n`` items into the universe ``[0, N)`` with ``N = ⌈n / p⌉`` for the target
     false-positive rate ``p`` (a uniform fingerprint per item).
  2. Sort the fingerprints and drop duplicates.
  3. Store the **gaps** between consecutive (sorted) fingerprints. The gaps are very nearly
     geometric with mean ``N / n = 1/p``, so they compress beautifully with a
     **Golomb–Rice code** whose parameter is the optimum ``M ≈ ln2 · (N/n) = ln2 / p``:
     each gap ``g`` is written as ``g // M`` in unary then ``g % M`` in truncated binary.

The result reaches within ~``1.5`` bits of the ``log₂(1/p)`` information-theoretic lower
bound per item — *more compact than a Bloom filter* (which needs ``1.44 · log₂(1/p)``) — at
the cost of being **immutable once built** and ``O(n)``-decoded per query (the canonical use
is shipping a compact set over the wire, à la Chrome's CRLSet). ``contains`` re-hashes the
item and walks the decoded gap stream with an early exit, so it never returns a false
negative and false-positives at the measured rate ``≈ p``.

This is *different* from every existing membership filter on the platform — those are
mutable bit-array sketches; the GCS is a static, near-entropy-optimal *compressed encoding*.
Pure stdlib (``hashlib.blake2b`` for the fingerprints); thread-safe via a single
``threading.Lock``; deterministic given the seed.
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any, Iterable

_LN2 = math.log(2.0)


class GolombCodedSetError(Exception):
    """Raised for an invalid Golomb-Coded-Set operation / configuration. Detail on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(str(detail))


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


# ── bit I/O ──────────────────────────────────────────────────────────────────────────


class _BitWriter:
    """Append-only MSB-first bit stream backed by a ``bytearray``."""

    __slots__ = ("_buf", "_cur", "_nbits", "_total")

    def __init__(self) -> None:
        self._buf = bytearray()
        self._cur = 0
        self._nbits = 0
        self._total = 0

    def write_bit(self, bit: int) -> None:
        self._cur = (self._cur << 1) | (bit & 1)
        self._nbits += 1
        self._total += 1
        if self._nbits == 8:
            self._buf.append(self._cur)
            self._cur = 0
            self._nbits = 0

    def write_bits(self, value: int, count: int) -> None:
        for i in range(count - 1, -1, -1):
            self.write_bit((value >> i) & 1)

    def write_unary(self, q: int) -> None:
        # q one-bits then a terminating zero-bit.
        for _ in range(q):
            self.write_bit(1)
        self.write_bit(0)

    def finish(self) -> tuple[bytes, int]:
        """Flush the partial byte (zero-padded) and return ``(payload, total_bits)``."""
        if self._nbits:
            self._buf.append(self._cur << (8 - self._nbits))
            self._cur = 0
            self._nbits = 0
        return bytes(self._buf), self._total


class _BitReader:
    """MSB-first bit reader bounded to exactly ``total_bits`` real bits (ignores padding)."""

    __slots__ = ("_data", "_total", "pos")

    def __init__(self, data: bytes, total_bits: int) -> None:
        self._data = data
        self._total = total_bits
        self.pos = 0

    def read_bit(self) -> int:
        if self.pos >= self._total:
            raise GolombCodedSetError("bit stream exhausted")
        byte = self._data[self.pos >> 3]
        bit = (byte >> (7 - (self.pos & 7))) & 1
        self.pos += 1
        return bit

    def read_bits(self, count: int) -> int:
        v = 0
        for _ in range(count):
            v = (v << 1) | self.read_bit()
        return v

    def read_unary(self) -> int:
        q = 0
        while self.read_bit() == 1:
            q += 1
        return q

    def has_more(self) -> bool:
        return self.pos < self._total


class GolombCodedSet:
    """Compressed static set-membership structure (Golomb–Rice gap coding)."""

    def __init__(self, items: Iterable[Any] | None = None, p: float = 0.01,
                 seed: int = 0) -> None:
        self._validate(p, seed)
        self._p = float(p)
        self._seed = seed
        self._seed_bytes = repr(seed).encode("ascii")
        self._lock = threading.Lock()
        self._build_locked([] if items is None else items)

    # ── validation / hashing ─────────────────────────────────────────────────────────
    @staticmethod
    def _validate(p: Any, seed: Any) -> None:
        if not isinstance(p, (int, float)) or isinstance(p, bool):
            raise GolombCodedSetError("p must be a number")
        if not (0.0 < float(p) < 1.0):
            raise GolombCodedSetError("p must be in (0, 1)")
        if not _is_int(seed):
            raise GolombCodedSetError("seed must be an int")

    @staticmethod
    def _to_bytes(item: Any) -> bytes:
        # Type-tagged so int 1, str "1" and bytes b"1" never alias one another.
        if isinstance(item, bool):
            raise GolombCodedSetError("item must be str, bytes or int (not bool)")
        if isinstance(item, bytes):
            return b"b" + item
        if isinstance(item, str):
            return b"s" + item.encode("utf-8")
        if isinstance(item, int):
            return b"i" + repr(item).encode("ascii")
        raise GolombCodedSetError("item must be str, bytes or int")

    def _fingerprint(self, item: Any, n_universe: int) -> int:
        data = self._to_bytes(item)
        digest = hashlib.blake2b(self._seed_bytes + data, digest_size=16).digest()
        return int.from_bytes(digest, "big") % n_universe

    # ── build ─────────────────────────────────────────────────────────────────────────
    def _build_locked(self, items: Iterable[Any]) -> None:
        try:
            materialised = list(items)
        except TypeError as exc:
            raise GolombCodedSetError("items must be iterable") from exc

        n = len(materialised)
        # Universe size: N = ceil(n / p); at least 1 so hashing never divides by zero.
        n_universe = max(1, math.ceil(n / self._p)) if n else 1
        fingerprints = sorted({self._fingerprint(it, n_universe) for it in materialised})
        num_items = len(fingerprints)

        # Optimal Golomb parameter for geometric gaps of mean N/num_items ≈ 1/p.
        mean_gap = n_universe / num_items if num_items else 1.0
        golomb_m = max(1, round(_LN2 * mean_gap))

        writer = _BitWriter()
        prev = -1
        for fp in fingerprints:
            gap = fp - prev          # ≥ 1 (fingerprints are strictly increasing)
            prev = fp
            self._encode_gap(writer, gap, golomb_m)
        payload, total_bits = writer.finish()

        self._n_universe = n_universe
        self._golomb_m = golomb_m
        self._num_items = num_items
        self._payload = payload
        self._total_bits = total_bits

    @staticmethod
    def _encode_gap(writer: _BitWriter, gap: int, golomb_m: int) -> None:
        q, r = divmod(gap, golomb_m)
        writer.write_unary(q)
        if golomb_m == 1:
            return
        b = (golomb_m - 1).bit_length()
        cutoff = (1 << b) - golomb_m
        if r < cutoff:
            writer.write_bits(r, b - 1)
        else:
            writer.write_bits(r + cutoff, b)

    @staticmethod
    def _decode_gap(reader: _BitReader, golomb_m: int) -> int:
        q = reader.read_unary()
        if golomb_m == 1:
            return q * golomb_m
        b = (golomb_m - 1).bit_length()
        cutoff = (1 << b) - golomb_m
        x = reader.read_bits(b - 1)
        r = x if x < cutoff else ((x << 1) | reader.read_bit()) - cutoff
        return q * golomb_m + r

    def build(self, items: Iterable[Any]) -> None:
        """Rebuild the (static) set from ``items``, replacing any prior contents."""
        with self._lock:
            self._build_locked(items)

    # ── query ───────────────────────────────────────────────────────────────────────
    def contains(self, item: Any) -> bool:
        """Membership test — no false negatives; false-positives at rate ``≈ p``."""
        with self._lock:
            if self._num_items == 0:
                return False
            target = self._fingerprint(item, self._n_universe)
            reader = _BitReader(self._payload, self._total_bits)
            cur = -1
            m = self._golomb_m
            while reader.has_more():
                cur += self._decode_gap(reader, m)
                if cur == target:
                    return True
                if cur > target:
                    return False
            return False

    def __contains__(self, item: Any) -> bool:
        return self.contains(item)

    def reset(self, p: float | None = None, seed: int | None = None) -> None:
        """Clear to the empty set; optionally reconfigure ``p`` / ``seed``."""
        with self._lock:
            np_ = self._p if p is None else p
            ns = self._seed if seed is None else seed
            self._validate(np_, ns)
            self._p = float(np_)
            self._seed = ns
            self._seed_bytes = repr(ns).encode("ascii")
            self._build_locked([])

    # ── introspection ─────────────────────────────────────────────────────────────────
    def __len__(self) -> int:
        return self._num_items

    @property
    def p(self) -> float:
        return self._p

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def num_items(self) -> int:
        return self._num_items

    @property
    def universe(self) -> int:
        return self._n_universe

    @property
    def golomb_m(self) -> int:
        return self._golomb_m

    @property
    def num_bits(self) -> int:
        return self._total_bits

    def bits_per_item(self) -> float:
        """Compressed size in bits divided by the number of stored fingerprints."""
        with self._lock:
            return self._total_bits / self._num_items if self._num_items else 0.0

    def stats(self) -> dict:
        """Summary: ``p`` / ``num_items`` / ``universe`` / ``golomb_m`` / ``num_bits`` /
        ``bits_per_item`` / ``seed``."""
        with self._lock:
            bpi = self._total_bits / self._num_items if self._num_items else 0.0
            return {
                "p": self._p,
                "num_items": self._num_items,
                "universe": self._n_universe,
                "golomb_m": self._golomb_m,
                "num_bits": self._total_bits,
                "bits_per_item": round(bpi, 6),
                "seed": self._seed,
            }
