"""Analogy Engine — probabilistic relational analogy discovery (cognitive layer).

The OS's *analogy* primitive: it stores observed "source → target" concept pairs
and retrieves them by relational similarity. For an item pair (X, Y) the engine
answers "have I seen a similar *relationship* before?" and can suggest completions
for "A is to B as C is to ?".

It **composes** MinHash (Jaccard similarity on both source and target token sets):

  analogize(X, Y) score = 0.5 · jaccard(X, stored_source) + 0.5 · jaccard(Y, stored_target)

  complete(X) = aggregate targets from analogies where stored_source ≈ X

**Honest scope.** This is statistical relational recall — not semantic
understanding, not an LLM. The "analogy" is pattern-matching over token-set
overlap, grounded in Jaccard similarity. No embeddings, no meaning.

Design: deterministic given seed; thread-safe (one RLock); imports and composes
MinHash — never reimplements it.
"""

from __future__ import annotations

import threading
from typing import Any

from pradyos.core.minhash import MinHash

__all__ = ["AnalogyEngine", "AnalogyEngineError"]


class AnalogyEngineError(Exception):
    """Raised on invalid AnalogyEngine operations."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _jaccard(sig_a: list[int], sig_b: list[int]) -> float:
    if not sig_a or not sig_b:
        return 0.0
    n = min(len(sig_a), len(sig_b))
    if n == 0:
        return 0.0
    eq = sum(1 for i in range(n) if sig_a[i] == sig_b[i])
    return eq / n


class AnalogyEngine:
    """Relational analogy store: MinHash Jaccard over source→target pairs.

    Space: O(num_hashes × stored_analogies). Thread-safe.
    """

    def __init__(
        self,
        num_hashes: int = 128,
        capacity: int = 10_000,
        seed: int = 0,
    ) -> None:
        if not isinstance(num_hashes, int) or num_hashes <= 0:
            raise AnalogyEngineError("num_hashes must be a positive integer")
        if not isinstance(capacity, int) or capacity <= 0:
            raise AnalogyEngineError("capacity must be a positive integer")
        self._n = num_hashes
        self._cap = capacity
        self._seed = int(seed)
        self._mh = MinHash(num_hashes=num_hashes, seed=seed)
        self._analogies: dict[str, dict[str, Any]] = {}
        self._seq = 0
        self._lock = threading.RLock()

    def _signature(self, tokens: list[str]) -> list[int]:
        mh = MinHash(num_hashes=self._n, seed=self._seed)
        mh.add_many("_q", tokens or [])
        return mh.signature("_q") or [0] * self._n

    def observe(
        self, analogy_id: str, source_tokens: list[str], target_tokens: list[str]
    ) -> None:
        """Store an analogy ``source_tokens → target_tokens`` under ``analogy_id``."""
        if not _is_str(analogy_id):
            raise AnalogyEngineError("analogy_id must be a non-empty string")
        if not isinstance(source_tokens, (list, tuple)):
            raise AnalogyEngineError("source_tokens must be a list of strings")
        if not isinstance(target_tokens, (list, tuple)):
            raise AnalogyEngineError("target_tokens must be a list of strings")
        src_sig = self._signature([str(t) for t in source_tokens])
        tgt_sig = self._signature([str(t) for t in target_tokens])
        with self._lock:
            self._seq += 1
            existing = self._analogies.get(analogy_id)
            freq = (existing["freq"] + 1) if existing else 1
            self._analogies[analogy_id] = {
                "source_tokens": [str(t) for t in source_tokens],
                "target_tokens": [str(t) for t in target_tokens],
                "source_sig": src_sig,
                "target_sig": tgt_sig,
                "freq": freq,
                "seq": self._seq,
            }
            if len(self._analogies) > self._cap:
                self._evict_one()

    def _evict_one(self) -> None:
        victim = min(
            self._analogies.items(), key=lambda kv: (kv[1]["freq"], kv[1]["seq"])
        )
        del self._analogies[victim[0]]

    def analogize(
        self,
        source_tokens: list[str],
        target_tokens: list[str],
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Find stored analogies whose source matches query source AND target matches query target."""
        if not isinstance(source_tokens, (list, tuple)):
            raise AnalogyEngineError("source_tokens must be a list of strings")
        if not isinstance(target_tokens, (list, tuple)):
            raise AnalogyEngineError("target_tokens must be a list of strings")
        if not isinstance(top_k, int) or top_k <= 0:
            raise AnalogyEngineError("top_k must be a positive integer")
        q_src_sig = self._signature([str(t) for t in source_tokens])
        q_tgt_sig = self._signature([str(t) for t in target_tokens])
        with self._lock:
            scored: list[dict[str, Any]] = []
            for aid, it in self._analogies.items():
                src_jac = _jaccard(q_src_sig, it["source_sig"])
                tgt_jac = _jaccard(q_tgt_sig, it["target_sig"])
                score = 0.5 * src_jac + 0.5 * tgt_jac
                if score >= min_score:
                    scored.append(
                        {
                            "analogy_id": aid,
                            "score": round(score, 6),
                            "source_jaccard": round(src_jac, 6),
                            "target_jaccard": round(tgt_jac, 6),
                            "source_tokens": it["source_tokens"],
                            "target_tokens": it["target_tokens"],
                            "freq": it["freq"],
                        }
                    )
        scored.sort(key=lambda d: (d["score"], d["freq"], d["analogy_id"]), reverse=True)
        return scored[:top_k]

    def complete(
        self,
        source_tokens: list[str],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Given source concept tokens, suggest likely target completions.

        Finds analogies whose stored source is similar to ``source_tokens`` and
        aggregates their targets, weighted by source Jaccard × analogy frequency.
        """
        if not isinstance(source_tokens, (list, tuple)):
            raise AnalogyEngineError("source_tokens must be a list of strings")
        if not isinstance(top_k, int) or top_k <= 0:
            raise AnalogyEngineError("top_k must be a positive integer")
        q_sig = self._signature([str(t) for t in source_tokens])
        with self._lock:
            completions: dict[str, dict[str, Any]] = {}
            for it in self._analogies.values():
                src_jac = _jaccard(q_sig, it["source_sig"])
                if src_jac <= 0.0:
                    continue
                tgt_key = " ".join(it["target_tokens"])
                existing = completions.get(tgt_key)
                weight = src_jac * it["freq"]
                if existing:
                    existing["weight"] += weight
                    existing["source_freq"] += 1
                else:
                    completions[tgt_key] = {
                        "target_tokens": it["target_tokens"],
                        "weight": weight,
                        "source_freq": 1,
                    }
        result = sorted(
            completions.values(), key=lambda d: d["weight"], reverse=True
        )
        for r in result:
            r["weight"] = round(r["weight"], 6)
        return result[:top_k]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._analogies),
                "capacity": self._cap,
                "num_hashes": self._n,
                "seed": self._seed,
            }

    def reset(self) -> None:
        with self._lock:
            self._analogies.clear()
            self._seq = 0

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._analogies)
