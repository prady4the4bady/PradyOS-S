"""Frequency-Aware Attention — streaming attention over a token stream (cognitive layer).

The OS's *attention* primitive: what matters most in a real-time stream of tokens,
maintained in O(1) per token and sub-linear space. It **composes** the shipped
Count-Sketch (signed-median frequency estimation — unbiased, unlike Count-Min's
positive bias) and adds **exponential decay** so attention fades unless refreshed.

Weight model (why it is built this way):

  weight(t) = 1 − exp(−κ · estimate(t) · s)

an *absolute, saturating* function of the decayed frequency, where ``s`` is a
global decay scale (starts at 1.0). ``decay()`` shrinks ``s`` so *every* weight
drops; ``attend(t)`` raises ``estimate(t)`` so a refreshed token recovers. A naive
max-normalised weight would be invariant under uniform decay (the ratio cancels),
so it could never *fade* — the absolute saturating form is what makes forgetting
real. κ (``sensitivity``) sets the half-attention point (≈ ln2/κ observations).

**Honest scope.** Statistical streaming attention with bounded error — *not*
transformer attention, no learned queries/keys, no semantics. The label is
"probabilistic cognitive runtime".

Design: imports CountSketch (never reimplements it); deterministic given a seed;
thread-safe (one RLock guards all state); a bounded seen-set enumerates concepts
for top-k, evicting the lowest-weight token past ``capacity``.
"""

from __future__ import annotations

import math
import threading
from typing import Any

from pradyos.core.count_sketch import CountSketch

__all__ = ["AttentionSketch", "AttentionSketchError"]


class AttentionSketchError(Exception):
    """Raised on invalid AttentionSketch operations."""


class AttentionSketch:
    """Streaming frequency attention with exponential decay (wraps CountSketch)."""

    def __init__(
        self,
        width: int = 2048,
        depth: int = 7,
        decay_factor: float = 0.99,
        sensitivity: float = 0.01,
        capacity: int = 100_000,
        seed: int = 0,
    ) -> None:
        if not isinstance(width, int) or width <= 0:
            raise AttentionSketchError("width must be a positive integer")
        if not isinstance(depth, int) or depth <= 0:
            raise AttentionSketchError("depth must be a positive integer")
        if not (isinstance(decay_factor, (int, float)) and 0.0 < decay_factor <= 1.0):
            raise AttentionSketchError("decay_factor must be in (0, 1]")
        if not (isinstance(sensitivity, (int, float)) and sensitivity > 0.0):
            raise AttentionSketchError("sensitivity must be positive")
        if not isinstance(capacity, int) or capacity <= 0:
            raise AttentionSketchError("capacity must be a positive integer")
        self._cs = CountSketch(width=width, depth=depth, seed=seed)
        self._decay = float(decay_factor)
        self._k = float(sensitivity)
        self._cap = capacity
        self._seed = int(seed)
        self._scale = 1.0
        self._total = 0
        self._decay_steps = 0
        self._seen: set[str] = set()
        self._lock = threading.RLock()

    # ── stream ─────────────────────────────────────────────────────────────────

    def attend(self, tokens: list[str]) -> None:
        """Process a stream of tokens (O(1) per token), updating attention."""
        if not isinstance(tokens, (list, tuple)):
            raise AttentionSketchError("tokens must be a list of strings")
        with self._lock:
            for tok in tokens:
                t = str(tok)
                self._cs.update(t, 1)
                self._seen.add(t)
                self._total += 1
            if len(self._seen) > self._cap:
                self._evict()

    def _evict(self) -> None:
        # drop the lowest-current-weight tokens back down to capacity
        ranked = sorted(self._seen, key=self._weight_locked)
        for t in ranked[: len(self._seen) - self._cap]:
            self._seen.discard(t)

    # ── read ───────────────────────────────────────────────────────────────────

    def _weight_locked(self, token: str) -> float:
        est = self._cs.estimate(token)
        if est <= 0:
            return 0.0
        return 1.0 - math.exp(-self._k * est * self._scale)

    def weight(self, token: str) -> float:
        """Normalised attention weight in [0, 1] for any token."""
        with self._lock:
            return self._weight_locked(str(token))

    def top_concepts(self, k: int = 10) -> list[tuple[str, float]]:
        """Top-k (token, weight) pairs by current attention, highest first."""
        if not isinstance(k, int) or k <= 0:
            raise AttentionSketchError("k must be a positive integer")
        with self._lock:
            scored = [(t, self._weight_locked(t)) for t in self._seen]
        scored.sort(key=lambda tw: (tw[1], tw[0]), reverse=True)
        return scored[:k]

    def decay(self) -> None:
        """Apply one exponential-decay step (every weight fades)."""
        with self._lock:
            self._scale *= self._decay
            self._decay_steps += 1

    # ── introspection ──────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_tokens": self._total,
                "unique_tracked": len(self._seen),
                "decay_steps": self._decay_steps,
                "scale": round(self._scale, 8),
                "decay_factor": self._decay,
                "sensitivity": self._k,
                "capacity": self._cap,
                "seed": self._seed,
                "count_sketch": self._cs.stats(),
            }

    def reset(self) -> None:
        with self._lock:
            self._cs.reset()
            self._seen.clear()
            self._scale = 1.0
            self._total = 0
            self._decay_steps = 0
