#!/usr/bin/env python3
"""Demo: Cognitive Layer self-healing — Novelty + Analogy + Compression.

Simulates a system observing a stream of events, using the three cognitive
primitives to detect anomalies, recall similar past patterns, and compress
the experience for long-term memory.

Run:
    python scripts/demo_cognitive_layer.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure project root is on the path (works when run as `python scripts/demo_*.py`)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from pradyos.core.novelty_detector import NoveltyDetector
from pradyos.core.analogy_engine import AnalogyEngine
from pradyos.core.compression_controller import CompressionController


def heading(label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")


def step(msg: str) -> None:
    print(f"  \u2022 {msg}")


def main() -> None:
    print("PRADY OS — Cognitive Layer Self-Healing Demo")
    print("=" * 60)

    nd = NoveltyDetector(seed=0)
    ae = AnalogyEngine(seed=0)
    cc = CompressionController(topk_k=10, seed=0)

    # ── Phase 1: normal baseline ──────────────────────────────────────
    heading("Phase 1: Learning normal patterns")
    normal_events = [
        "heartbeat_ok",
        "heartbeat_ok",
        "cpu_usage_45pct",
        "mem_usage_60pct",
        "heartbeat_ok",
        "disk_read_50ms",
        "heartbeat_ok",
        "cpu_usage_42pct",
    ]
    step(f"Observing {len(normal_events)} normal events...")
    for ev in normal_events:
        nd.observe(ev)
    step(f"Novelty rate: {nd.novelty_rate():.2%}")
    step(f"Unique estimate: {nd.stats()['unique_estimate']}")

    ae.observe("pattern_1", ["heartbeat", "normal"], ["ok", "stable"])
    ae.observe("pattern_2", ["cpu", "medium"], ["usage", "typical"])
    step(f"Stored {ae.stats()['size']} analogy patterns")

    cc.feed(normal_events, "topk")
    topk = cc.summarize("topk")
    step(f"Top-K summary: {len(topk['items'])} frequent items tracked")

    # ── Phase 2: anomaly detection ────────────────────────────────────
    heading("Phase 2: Novelty detection — anomalous event")
    anomaly = "cpu_usage_98pct"
    is_new = nd.is_novel(anomaly)
    step(f"'{anomaly}' is novel? {is_new}")
    nd.observe(anomaly)
    surprise = nd.surprise_score(anomaly)
    step(f"Surprise score: {surprise:.1f} (higher = more surprising)")

    # ── Phase 3: analogy recall ───────────────────────────────────────
    heading("Phase 3: Analogy recall — similar past patterns")
    results = ae.analogize(["cpu", "high"], ["usage", "spike"])
    step(f"Found {len(results)} similar analogies")
    for r in results:
        step(f"  {r['analogy_id']}: score={r['score']:.3f}, "
             f"src_jac={r['source_jaccard']:.3f}")

    completions = ae.complete(["cpu", "high"])
    step(f"Completion suggestions: {len(completions)}")
    for c in completions:
        tokens = " ".join(c["target_tokens"])
        step(f"  \"cpu high\" -> \"{tokens}\" (weight={c['weight']:.3f})")

    # ── Phase 4: compression ──────────────────────────────────────────
    heading("Phase 4: Compression — summarise for long-term memory")
    all_events = normal_events + [anomaly]
    for _ in range(3):
        all_events.extend(normal_events)

    step(f"Total events: {len(all_events)}")
    for strategy in cc.strategies():
        est = cc.estimate_size(all_events, strategy)
        step(f"  {strategy}: {est['raw_bytes']}B raw -> "
             f"{est['estimated_compressed_bytes']}B compressed "
             f"(ratio={est['compression_ratio']:.4f})")

    cc.feed(all_events, "bloom")
    bstats = cc.summarize("bloom")
    step(f"Bloom: {bstats['total_fed']} items -> "
         f"{bstats['unique_estimate']} unique estimates")

    # ── summary ───────────────────────────────────────────────────────
    heading("Summary")
    print(f"  NoveltyDetector:     {nd.stats()['total_observations']} observations, "
          f"{nd.stats()['unique_estimate']} unique")
    print(f"  AnalogyEngine:       {ae.stats()['size']} stored analogies")
    print(f"  CompressionController: {cc.stats()['active_strategies']}")
    print(f"\n  All three cognitive primitives operational.")


if __name__ == "__main__":
    main()
