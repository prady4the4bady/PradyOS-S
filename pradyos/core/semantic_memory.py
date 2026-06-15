"""Semantic Memory Engine — probabilistic associative recall (cognitive layer).

The OS's episodic + semantic memory *primitive*. It composes two shipped
sub-linear structures — MinHash (set-level Jaccard similarity) and SimHash
(bit-fingerprint Hamming similarity) — into a single associative store that
answers "have I seen something like this before?" in sub-linear space.

  combined_score = 0.6 · jaccard(MinHash) + 0.4 · (1 − hamming/bits)

MinHash catches *set-similar* content (shared tokens regardless of order);
SimHash catches *near-duplicate* fingerprints. Together they recall items that
either share vocabulary or are bitwise-close, which neither does alone.

**Honest scope.** This is statistical associative recall with bounded error — a
real memory primitive — *not* grounded semantic understanding. No embeddings, no
language model, no meaning. The label is "probabilistic cognitive runtime".

Design (matches the rest of the codebase): dependency-free beyond the two
substrate classes it *imports* (never reimplements); deterministic given a seed;
thread-safe (one RLock guards all state); pure comparisons on stored signatures
so recall touches no shared mutable substrate.
"""

from __future__ import annotations

import threading
from typing import Any

from pradyos.core.minhash import MinHash
from pradyos.core.simhash import SimHash

__all__ = ["SemanticMemory", "SemanticMemoryError"]


class SemanticMemoryError(Exception):
    """Raised on invalid SemanticMemory operations."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _jaccard(sig_a: list[int], sig_b: list[int]) -> float:
    """MinHash Jaccard estimate = fraction of equal signature positions."""
    if not sig_a or not sig_b:
        return 0.0
    n = min(len(sig_a), len(sig_b))
    if n == 0:
        return 0.0
    eq = sum(1 for i in range(n) if sig_a[i] == sig_b[i])
    return eq / n


class SemanticMemory:
    """Associative memory: MinHash (Jaccard) + SimHash (Hamming) recall.

    Space: O(num_hashes × stored_items). Recall: O(stored_items) with early
    filtering by ``min_similarity`` and a top-k cut.
    """

    def __init__(
        self,
        num_hashes: int = 128,
        simhash_bits: int = 64,
        capacity: int = 10_000,
        seed: int = 0,
    ) -> None:
        if not isinstance(num_hashes, int) or num_hashes <= 0:
            raise SemanticMemoryError("num_hashes must be a positive integer")
        if not isinstance(simhash_bits, int) or simhash_bits <= 0:
            raise SemanticMemoryError("simhash_bits must be a positive integer")
        if not isinstance(capacity, int) or capacity <= 0:
            raise SemanticMemoryError("capacity must be a positive integer")
        self._n = num_hashes
        self._bits = simhash_bits
        self._cap = capacity
        self._seed = int(seed)
        # key -> {content, tokens(set), sig(list[int]), fp(int), freq(int), seq(int)}
        self._items: dict[str, dict[str, Any]] = {}
        self._seq = 0
        self._lock = threading.RLock()

    # ── signature / fingerprint helpers (compose the substrate, fresh + det.) ──

    def _signature(self, tokens: list[str]) -> list[int]:
        mh = MinHash(num_hashes=self._n, seed=self._seed)
        mh.add_many("_q", tokens or [])
        return mh.signature("_q") or [0] * self._n

    def _fingerprint(self, tokens: list[str]) -> int:
        sh = SimHash(num_bits=self._bits, seed=self._seed)
        sh.hash("_q", list(tokens or []))
        return sh.fingerprint("_q") or 0

    def _hamming_sim(self, fp_a: int, fp_b: int) -> float:
        # Raw bit-agreement floors at ~0.5 for unrelated docs (chance), so a naive
        # (1 − hamming/bits) would prop up unrelated scores. Rescale to a SIGNAL in
        # [0,1] where chance-agreement (0.5) → 0 and identical (1.0) → 1.0:
        #   signal = max(0, 2·agreement − 1).
        agreement = 1.0 - (bin(fp_a ^ fp_b).count("1") / self._bits)
        return max(0.0, 2.0 * agreement - 1.0)

    # ── write ──────────────────────────────────────────────────────────────────

    def store(self, key: str, content: str, tokens: list[str]) -> None:
        """Store ``content`` under ``key`` with MinHash + SimHash fingerprints.

        Re-storing an existing key refreshes it and bumps its frequency."""
        if not _is_str(key):
            raise SemanticMemoryError("key must be a non-empty string")
        if not isinstance(tokens, (list, tuple)):
            raise SemanticMemoryError("tokens must be a list of strings")
        toks = [str(t) for t in tokens]
        sig = self._signature(toks)
        fp = self._fingerprint(toks)
        with self._lock:
            self._seq += 1
            existing = self._items.get(key)
            freq = (existing["freq"] + 1) if existing else 1
            self._items[key] = {
                "content": str(content),
                "tokens": set(toks),
                "sig": sig,
                "fp": fp,
                "freq": freq,
                "seq": self._seq,
            }
            if len(self._items) > self._cap:
                self._evict_one()

    def _evict_one(self) -> None:
        # drop the least-frequent (tie → oldest) item to stay within capacity
        victim = min(self._items.items(), key=lambda kv: (kv[1]["freq"], kv[1]["seq"]))
        del self._items[victim[0]]

    # ── read ───────────────────────────────────────────────────────────────────

    def recall(
        self, query_tokens: list[str], top_k: int = 10, min_similarity: float = 0.0
    ) -> list[dict[str, Any]]:
        """Return the top-k stored items most similar to ``query_tokens``."""
        if not isinstance(query_tokens, (list, tuple)):
            raise SemanticMemoryError("query_tokens must be a list of strings")
        if not isinstance(top_k, int) or top_k <= 0:
            raise SemanticMemoryError("top_k must be a positive integer")
        q_sig = self._signature([str(t) for t in query_tokens])
        q_fp = self._fingerprint([str(t) for t in query_tokens])
        with self._lock:
            scored: list[dict[str, Any]] = []
            for key, it in self._items.items():
                jac = _jaccard(q_sig, it["sig"])
                ham = self._hamming_sim(q_fp, it["fp"])
                score = 0.6 * jac + 0.4 * ham
                if score >= min_similarity:
                    scored.append(
                        {
                            "key": key,
                            "score": round(score, 6),
                            "jaccard": round(jac, 6),
                            "hamming_sim": round(ham, 6),
                            "content": it["content"],
                            "freq": it["freq"],
                        }
                    )
        scored.sort(key=lambda d: (d["score"], d["freq"], d["key"]), reverse=True)
        return scored[:top_k]

    def forget(self, frequency_threshold: float) -> int:
        """Prune items whose store-frequency is below ``frequency_threshold``.

        Frequency here is an *exact* per-key store count (strictly better than an
        approximate Count-Min counter, since keys are explicitly tracked)."""
        with self._lock:
            doomed = [k for k, it in self._items.items() if it["freq"] < frequency_threshold]
            for k in doomed:
                del self._items[k]
        return len(doomed)

    def merge(self, other: "SemanticMemory") -> None:
        """Merge another memory in-place (distributed use). Higher freq wins."""
        if not isinstance(other, SemanticMemory):
            raise SemanticMemoryError("can only merge another SemanticMemory")
        if other._n != self._n or other._bits != self._bits or other._seed != self._seed:
            raise SemanticMemoryError("cannot merge memories with different config")
        with self._lock, other._lock:
            for key, it in other._items.items():
                cur = self._items.get(key)
                if cur is None or it["freq"] > cur["freq"]:
                    self._seq += 1
                    self._items[key] = {**it, "seq": self._seq}
            while len(self._items) > self._cap:
                self._evict_one()

    # ── introspection ──────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            items = list(self._items.values())
            concepts = sorted(items, key=lambda it: it["freq"], reverse=True)[:5]
            return {
                "size": len(items),
                "capacity": self._cap,
                "num_hashes": self._n,
                "simhash_bits": self._bits,
                "seed": self._seed,
                "top_concepts": [
                    {"key": k, "freq": it["freq"]}
                    for k, it in sorted(
                        self._items.items(), key=lambda kv: kv[1]["freq"], reverse=True
                    )[:5]
                ]
                if items
                else [],
                "avg_freq": round(sum(it["freq"] for it in items) / len(items), 4)
                if items
                else 0.0,
            }

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._items)

    def reset(self) -> None:
        with self._lock:
            self._items.clear()
            self._seq = 0
