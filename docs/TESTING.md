# Testing

PradySovereign has a large test suite (~430 test files). Most tests are fast
unit tests; a few are integration or timing-sensitive.

## Quick commands

```bash
# Full suite (20-25 min on typical hardware)
pytest tests/ -x --tb=short -q

# Proving ground — runs the canonical module list
python scripts/prove.py

# With benchmarks
python scripts/prove.py --benchmark

# Benchmarks only
python scripts/benchmarks.py --json
```

## What `prove.py` covers

`scripts/prove.py` runs ~300 modules sequentially via subprocess (one `pytest`
invocation per module). It covers:

- **Core probabilistic structures**: BloomFilter, MinHash, HyperLogLog,
  CountSketch, TDigest, DDSketch, and 60+ more data-structure modules.
- **Cognitive layer**: SemanticMemory, AttentionSketch, ExperienceDistribution,
  NoveltyDetector, AnalogyEngine, CompressionController.
- **Autonomy layers (L1-L6)**: Skills, Foresight, Drive, Critic, Causality,
  Reverie, Ascent, Evolve.
- **Infrastructure**: Guild, Codemap, Licensing, Web routers, CLI, AEGIS,
  Bastion, Quasar Gate, Starmap, Nexus Weave, etc.
- **Integration**: Campaign engine, Memory Citadel, Self-heal, Redis bus, etc.

## Test results (HEAD 76e4bfb, verified June 2026)

| Suite | Tests | Result | Time |
|-------|-------|--------|------|
| Core probabilistic (unit) | 213 | PASS | 5s |
| Cognitive layer (unit) | 218 | PASS | 11s |
| Guild + Skills + Codemap | 72 | PASS | 1s |
| Autonomy layers (L1-L6) | 113 | PASS | 12s |
| Core + cognitive web | 195 | PASS | 83s |
| Guild/skills/codemap web | 29 | PASS | 1s |
| Licensing + billing | 37 | PASS | 5s |
| **Subtotal (targeted)** | **877** | **PASS** | ~2 min |
| Full suite (timeboxed 20 min) | ~73% observed | all `.`, no `F` | >20 min |
| Benchmarks (8 internal) | 8/8 | PASS | 3.3s |

## Notes

- **Full suite size**: ~430 test files. On a loaded Windows machine this takes
  20-25 minutes. All observed tests pass (dots). Timeout-limited runs show no
  failures.
- **Known slow**: `test_lifespan_web` (~66s), `test_oracle_live` (network).
- **Known flakes** (pass on isolated re-run):
  - `test_near_constant_time_performance` (timing-sensitive)
  - `test_oracle_live` (network availability)
  - `test_treap_web` (host resource contention)
- **Skipped tests**: `test_oracle_live` is skipped when no network is available.
- **Contributor guideline**: Run `python scripts/prove.py` plus the benchmark
  suite before committing. If time is limited, run the targeted subsets above.
