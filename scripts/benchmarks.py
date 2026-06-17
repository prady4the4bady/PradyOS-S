#!/usr/bin/env python3
"""PradySovereign — Reproducible Internal Benchmarks.

Measures throughput and correctness of core data structures using fixed
seeds.  Each benchmark returns PASS/FAIL based on minimum-performance
thresholds.  No external competitors are executed.

Usage
-----
    python scripts/benchmarks.py              # run all
    python scripts/benchmarks.py --fast       # stop on first failure
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SEED = 42
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report(name: str, ops: int, elapsed: float, threshold: float) -> bool:
    rate = ops / elapsed if elapsed > 0 else float("inf")
    ok = rate >= threshold
    status = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  {status}  {BOLD}{name:<40}{RESET}  {rate:>10.0f} ops/s  (>={threshold:.0f})")
    return ok


def _report_correct(name: str, ok: bool) -> bool:
    status = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  {status}  {BOLD}{name:<40}{RESET}")
    return ok


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def bench_bloom_filter() -> bool:
    from pradyos.core.bloom_filter import BloomFilter

    rng = random.Random(SEED)
    data = [rng.randint(0, 1 << 63) for _ in range(5000)]
    bf = BloomFilter(capacity=len(data), error_rate=0.01)

    t0 = time.monotonic()
    for v in data:
        bf.add(v)
    t_add = time.monotonic() - t0

    t0 = time.monotonic()
    ok = sum(1 for v in data if bf.contains(v))
    t_check = time.monotonic() - t0

    added_ok = _report("BloomFilter add", len(data), t_add, 50_000)
    check_ok = _report("BloomFilter contains", len(data), t_check, 50_000)
    correct = _report_correct("BloomFilter recall", ok == len(data))
    return added_ok and check_ok and correct


def bench_minhash() -> bool:
    from pradyos.core.minhash import MinHash

    rng = random.Random(SEED)
    mh = MinHash(num_hashes=128, seed=SEED)

    t0 = time.monotonic()
    for i in range(100):
        name = f"set_{i}"
        for _ in range(100):
            mh.add(name, rng.randint(0, 1 << 20))
    t_add = time.monotonic() - t0

    t0 = time.monotonic()
    for i in range(99):
        mh.similarity(f"set_{i}", f"set_{i + 1}")
    t_sim = time.monotonic() - t0

    add_ok = _report("MinHash add", 100 * 100, t_add, 5000)
    sim_ok = _report("MinHash similarity", 99, t_sim, 500)
    return add_ok and sim_ok


def bench_hyperloglog() -> bool:
    from pradyos.core.hyperloglog import HyperLogLog

    rng = random.Random(SEED)
    data = [rng.randint(0, 1 << 31) for _ in range(10_000)]
    hll = HyperLogLog(precision=12)

    t0 = time.monotonic()
    for v in data:
        hll.add(v)
    t_add = time.monotonic() - t0

    t0 = time.monotonic()
    for _ in range(100):
        hll.estimate()
    t_est = time.monotonic() - t0

    add_ok = _report("HyperLogLog add", len(data), t_add, 30_000)
    est_ok = _report("HyperLogLog estimate", 100, t_est, 500)
    actual = max(1, len(set(data)))
    estimated = hll.estimate()
    err = abs(estimated - actual) / actual
    correct = _report_correct(f"HyperLogLog error {err:.4f}", err < 0.05)
    return add_ok and est_ok and correct


def bench_count_sketch() -> bool:
    from pradyos.core.count_sketch import CountSketch

    rng = random.Random(SEED)
    items = [rng.randint(0, 1 << 16) for _ in range(5000)]
    cs = CountSketch(depth=5, width=2048)

    t0 = time.monotonic()
    for v in items:
        cs.update(v)
    t_update = time.monotonic() - t0

    t0 = time.monotonic()
    for v in items[:1000]:
        cs.estimate(v)
    t_est = time.monotonic() - t0

    update_ok = _report("CountSketch update", len(items), t_update, 30_000)
    est_ok = _report("CountSketch estimate", 1000, t_est, 2000)
    return update_ok and est_ok


def bench_tdigest() -> bool:
    from pradyos.core.tdigest import TDigest

    rng = random.Random(SEED)
    data = [rng.gauss(0, 1) for _ in range(10_000)]
    td = TDigest(compression=100.0)

    t0 = time.monotonic()
    for v in data:
        td.add(v)
    t_add = time.monotonic() - t0

    t0 = time.monotonic()
    for p in [1, 5, 25, 50, 75, 95, 99]:
        td.percentile(p)
    t_pctl = time.monotonic() - t0

    add_ok = _report("TDigest add", len(data), t_add, 4000)
    pctl_ok = _report("TDigest percentile", 7, t_pctl, 200)
    return add_ok and pctl_ok


def bench_novelty_detector() -> bool:
    from pradyos.core.novelty_detector import NoveltyDetector

    rng = random.Random(SEED)
    nd = NoveltyDetector(bloom_capacity=5000, bloom_error_rate=0.01)
    data = [str(rng.randint(0, 1 << 20)) for _ in range(3000)]

    t0 = time.monotonic()
    for v in data:
        nd.observe(v)
    t_obs = time.monotonic() - t0

    t0 = time.monotonic()
    for v in data[:500]:
        nd.surprise_score(v)
    t_score = time.monotonic() - t0

    obs_ok = _report("NoveltyDetector observe", len(data), t_obs, 20_000)
    score_ok = _report("NoveltyDetector surprise_score", 500, t_score, 400)
    return obs_ok and score_ok


def bench_analogy_engine() -> bool:
    from pradyos.core.analogy_engine import AnalogyEngine

    rng = random.Random(SEED)
    ae = AnalogyEngine()

    pairs: list[tuple[str, list[str], list[str]]] = []
    for i in range(200):
        src = [f"tok_{rng.randint(0, 100)}" for _ in range(5)]
        tgt = [f"tok_{rng.randint(0, 100)}" for _ in range(5)]
        pairs.append((f"id_{i}", src, tgt))

    t0 = time.monotonic()
    for aid, src, tgt in pairs:
        ae.observe(aid, src, tgt)
    t_obs = time.monotonic() - t0

    t0 = time.monotonic()
    for _, src, tgt in pairs[:50]:
        ae.analogize(src, tgt, top_k=5)
    t_analogize = time.monotonic() - t0

    obs_ok = _report("AnalogyEngine observe", len(pairs), t_obs, 100)
    analogize_ok = _report("AnalogyEngine analogize", 50, t_analogize, 50)
    return obs_ok and analogize_ok


def bench_compression_controller() -> bool:
    from pradyos.core.compression_controller import CompressionController

    rng = random.Random(SEED)
    cc = CompressionController()
    data = [f"event-{rng.randint(0, 1000)}" for _ in range(3000)]

    t0 = time.monotonic()
    batches = [data[i:i + 500] for i in range(0, len(data), 500)]
    for batch in batches:
        cc.feed(batch)
    t_feed = time.monotonic() - t0

    t0 = time.monotonic()
    cc.summarize(strategy="topk")
    t_summary = time.monotonic() - t0

    feed_ok = _report("CompressionController feed", len(data), t_feed, 10_000)
    summary_ok = _report("CompressionController summarize", 1, t_summary, 50)
    return feed_ok and summary_ok


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_BENCHMARKS = [
    ("BloomFilter", bench_bloom_filter),
    ("MinHash", bench_minhash),
    ("HyperLogLog", bench_hyperloglog),
    ("CountSketch", bench_count_sketch),
    ("TDigest", bench_tdigest),
    ("NoveltyDetector", bench_novelty_detector),
    ("AnalogyEngine", bench_analogy_engine),
    ("CompressionController", bench_compression_controller),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmarks", description="PradySovereign internal benchmarks")
    parser.add_argument("--fast", "-f", action="store_true", help="stop on first failure")
    parser.add_argument("--list", action="store_true", help="list benchmark names and exit")
    parser.add_argument("--json", action="store_true", help="write results to benchmarks/results_prady.json")
    args = parser.parse_args(argv)

    if args.list:
        for name, _ in ALL_BENCHMARKS:
            print(name)
        return 0

    random.seed(SEED)
    print(f"\n{BOLD}PradySovereign — Internal Benchmarks{RESET}")
    print(f"{DIM}seed={SEED}{RESET}\n")

    passed = 0
    failed = 0
    results: list[dict[str, Any]] = []
    for name, fn in ALL_BENCHMARKS:
        print(f"  {BOLD}{name}{RESET}")
        t0 = time.monotonic()
        ok = fn()
        elapsed = time.monotonic() - t0
        if ok:
            passed += 1
        else:
            failed += 1
            if args.fast:
                print(f"\n{RED}Stopped on first failure.{RESET}")
                break
        results.append({"name": name, "passed": ok, "elapsed_seconds": round(elapsed, 3)})
        print()

    print(f"{BOLD}{'-' * 50}{RESET}")
    print(f"  {passed} passed, {failed} failed")

    if args.json:
        import json
        out = {
            "seed": SEED,
            "timestamp": time.time(),
            "passed": passed,
            "failed": failed,
            "results": results,
        }
        path = Path("benchmarks") / "results_prady.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"  Results written to {path}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
