# PradySovereign — Internal Benchmarks

Reproducible performance benchmarks for core data structures and cognitive
primitives.  No external competitors are run; these measure internal
throughput and correctness against self-defined thresholds.

## Running

```bash
# All benchmarks
python scripts/benchmarks.py

# Stop on first failure
python scripts/benchmarks.py --fast

# List available benchmarks
python scripts/benchmarks.py --list

# Via proving ground
python scripts/prove.py --benchmark
```

## Benchmarks

| Name                     | Measures                              | Threshold     |
|--------------------------|---------------------------------------|---------------|
| BloomFilter              | add + contains throughput, recall     | 50k ops/s     |
| MinHash                  | signature + jaccard throughput        | 200 sig/s     |
| HyperLogLog              | add + cardinality throughput, error   | 30k ops/s     |
| CountSketch              | add + query throughput                | 30k ops/s     |
| TDigest                  | add + percentile throughput           | 30k ops/s     |
| NoveltyDetector          | see + score throughput                | 20k ops/s     |
| AnalogyEngine            | learn + analogy throughput            | 200 learn/s   |
| CompressionController    | feed + summarise throughput           | 20k ops/s     |

All use fixed seed `42` for reproducibility.
