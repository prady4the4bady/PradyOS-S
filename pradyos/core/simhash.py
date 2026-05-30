"""Phase 89 — Sovereign SimHash.

Locality-sensitive fingerprints for **near-duplicate detection** (Charikar). A
document — a bag of feature tokens — is folded to a single ``num_bits`` integer
such that *similar documents have similar fingerprints*: for every token we take
a stable hash, and for each bit position cast a weighted vote (+1 if that bit of
the token hash is set, −1 otherwise); summing the votes over all tokens and then
thresholding the per-bit totals at zero yields the fingerprint. Because the votes
are summed, the fingerprint is a **bag-of-words** signature — token order does not
matter, but token frequency does.

The **Hamming distance** between two fingerprints (popcount of their XOR) measures
dissimilarity: identical documents share every bit (distance 0), near-duplicates
differ in only a handful of bits, and unrelated documents sit near ``num_bits / 2``
(random bits). The normalized similarity is ``1 − hamming / num_bits``. At 64 bits
a Hamming distance ≤ :data:`NEAR_DUPLICATE_HAMMING` is the conventional
near-duplicate cutoff (Manku et al.).

The token hash mixes in a ``seed`` (so signatures are deterministic yet injectable
for tests) and uses BLAKE2b — *not* the salted built-in ``hash`` — so a fingerprint
is reproducible across processes. This object is a multi-document store: it owns
the config plus one fingerprint per named document, so ``hash(name, tokens)``
computes and stores a fingerprint and ``similarity``/``hamming`` compare two stored
ones. Pure stdlib. Thread-safe via a single ``threading.Lock``; internal
``_locked`` helpers never re-acquire it.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any, Sequence

#: At num_bits=64, two fingerprints within this Hamming distance are near-duplicates.
NEAR_DUPLICATE_HAMMING = 3

_MAX_BITS = 512   # BLAKE2b yields at most 64 bytes (512 bits) per digest


class SimHashError(Exception):
    """Raised for an invalid SimHash configuration. The offending value is on ``detail``."""

    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__(f"invalid simhash configuration: {detail!r}")


def _is_pos_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class SimHash:
    """Multi-document SimHash store: bit-fingerprints + Hamming similarity."""

    def __init__(self, num_bits: int = 64, seed: int = 0) -> None:
        if not _is_pos_int(num_bits) or num_bits > _MAX_BITS:
            raise SimHashError(num_bits)
        if not _is_int(seed):
            raise SimHashError(seed)
        self._num_bits = num_bits
        self._seed = seed
        self._nbytes = (num_bits + 7) // 8
        self._docs: dict[str, int] = {}     # document name -> fingerprint (num_bits int)
        self._total = 0
        self._lock = threading.Lock()

    # ── internal helpers (pure / run under the lock; never re-acquire) ───────────
    def _token_hash(self, token: Any) -> int:
        data = repr((self._seed, token)).encode("utf-8")
        digest = hashlib.blake2b(data, digest_size=self._nbytes).digest()
        return int.from_bytes(digest, "big")

    def _fingerprint(self, tokens: Sequence[Any]) -> int:
        votes = [0] * self._num_bits
        for token in tokens:
            h = self._token_hash(token)
            for i in range(self._num_bits):
                if (h >> i) & 1:
                    votes[i] += 1
                else:
                    votes[i] -= 1
        fp = 0
        for i in range(self._num_bits):
            if votes[i] > 0:                # threshold at zero (ties → 0 bit)
                fp |= (1 << i)
        return fp

    def _hamming_locked(self, a: str, b: str) -> int | None:
        fa = self._docs.get(a)
        fb = self._docs.get(b)
        if fa is None or fb is None:
            return None
        return bin(fa ^ fb).count("1")

    # ── mutation ─────────────────────────────────────────────────────────────────
    def hash(self, doc_name: Any, tokens: Sequence[Any]) -> int:
        """Compute and store the fingerprint of ``tokens`` under ``doc_name``; return it."""
        fp = self._fingerprint(list(tokens))
        with self._lock:
            self._docs[str(doc_name)] = fp
            self._total += 1
        return fp

    def reset(self, num_bits: int | None = None, seed: int | None = None) -> None:
        """Clear all stored fingerprints; optionally reconfigure ``num_bits`` / ``seed``."""
        with self._lock:
            if num_bits is not None:
                if not _is_pos_int(num_bits) or num_bits > _MAX_BITS:
                    raise SimHashError(num_bits)
                self._num_bits = num_bits
                self._nbytes = (num_bits + 7) // 8
            if seed is not None:
                if not _is_int(seed):
                    raise SimHashError(seed)
                self._seed = seed
            self._docs = {}
            self._total = 0

    # ── queries ──────────────────────────────────────────────────────────────────
    def fingerprint(self, doc_name: Any) -> int | None:
        """The stored fingerprint for ``doc_name`` (or ``None`` if unknown)."""
        with self._lock:
            return self._docs.get(str(doc_name))

    def hamming(self, doc_a: Any, doc_b: Any) -> int | None:
        """Raw Hamming distance between two stored fingerprints (``None`` if either is unknown)."""
        with self._lock:
            return self._hamming_locked(str(doc_a), str(doc_b))

    def similarity(self, doc_a: Any, doc_b: Any) -> float | None:
        """Normalized similarity ``1 − hamming / num_bits`` (``None`` if either is unknown)."""
        with self._lock:
            dist = self._hamming_locked(str(doc_a), str(doc_b))
            return None if dist is None else 1 - dist / self._num_bits

    def near_duplicate(self, doc_a: Any, doc_b: Any,
                       threshold: int = NEAR_DUPLICATE_HAMMING) -> bool | None:
        """Whether two documents are within ``threshold`` Hamming bits (``None`` if unknown)."""
        with self._lock:
            dist = self._hamming_locked(str(doc_a), str(doc_b))
            return None if dist is None else dist <= threshold

    def documents(self) -> list[str]:
        """Sorted names of all stored documents."""
        with self._lock:
            return sorted(self._docs)

    def __len__(self) -> int:
        with self._lock:
            return len(self._docs)

    def __contains__(self, doc_name: Any) -> bool:
        with self._lock:
            return str(doc_name) in self._docs

    @property
    def num_bits(self) -> int:
        return self._num_bits

    @property
    def seed(self) -> int:
        return self._seed

    def stats(self) -> dict:
        """Summary: ``num_bits``, number of ``docs``, ``total_hashed`` calls, ``seed``."""
        with self._lock:
            return {
                "num_bits": self._num_bits,
                "docs": len(self._docs),
                "total_hashed": self._total,
                "seed": self._seed,
            }
