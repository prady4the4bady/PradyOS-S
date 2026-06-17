# PradySovereign — Internal Benchmarks

Reproducible performance benchmarks for core data structures and cognitive
primitives.  No external competitors are executed; each benchmark tests
throughput and correctness against self-defined thresholds.

## How to Run

```bash
# All benchmarks
python scripts/benchmarks.py

# With structured JSON result file
python scripts/benchmarks.py --json

# Via proving ground
python scripts/prove.py --benchmark

# List available benchmarks
python scripts/benchmarks.py --list
```

Structured results are written to `benchmarks/results_prady.json` when `--json`
is passed.  This file contains per-benchmark entries with:

| Field             | Description                        |
|-------------------|------------------------------------|
| `name`            | Benchmark name                     |
| `passed`          | `true` / `false`                   |
| `elapsed_seconds` | Wall-clock runtime for the group   |

## Benchmarks

| Benchmark                  | What It Tests                                                        | Metric               |
|----------------------------|----------------------------------------------------------------------|----------------------|
| BloomFilter                | Add throughput, contains throughput, 100 % recall rate               | ops/s, correctness   |
| MinHash                    | Add throughput (10 000 elements across 100 sets), similarity query   | ops/s                |
| HyperLogLog                | Add throughput, cardinality estimation throughput, estimation error  | ops/s, relative error|
| CountSketch                | Update throughput, frequency estimation throughput                   | ops/s                |
| TDigest                    | Add throughput, percentile query throughput                          | ops/s                |
| NoveltyDetector            | Observe throughput, surprise-score throughput                        | ops/s                |
| AnalogyEngine              | Observe throughput (200 analogies), analogize query throughput       | ops/s                |
| CompressionController      | Feed throughput (3 000 events in batches), summarise latency         | ops/s                |

All use fixed seed `42` for deterministic, cross-platform reproducibility.

## Results (latest run)

Results are stored in `benchmarks/results_prady.json` after `--json` runs and
are **not** committed to the repository (numbers are machine-dependent).
