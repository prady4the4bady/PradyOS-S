# PradySovereign

**A governed, self-improving cognitive layer for autonomous AI agents and dev swarms.**

## What it is

- **Six autonomy layers (L1-L6)**: Skills (learn from experience) → Foresight
  (predict action value) → Drive (self-propose goals, Sovereign-gated) →
  Critic (adversarial veto) → Causality (counterfactual credit assignment) →
  Reverie/Ascent (idle reflection + self-improvement loop).
- **Six cognitive primitives**: SemanticMemory (MinHash+SimHash),
  AttentionSketch (Count-Sketch+decay), ExperienceDistribution (T-Digest+DDSketch),
  NoveltyDetector (Bloom+HLL), AnalogyEngine (MinHash clusters),
  CompressionController (all sketches, dynamic budget).
- **Multi-agent guild** with role-based blackboard orchestration and a
  **Sovereign gate** that actually vetoes risky actions.
- **OS-style introspection**: metrics, codemap (AST scan of own source tree),
  audit logs, and a live governance chamber.

## Why it exists

Typical agent frameworks leave three gaps:

- **Opacity**: you can't trace why an agent chose a course of action.
- **No self-correction**: failures aren't analysed, so the same mistakes repeat.
- **Unchecked agency**: swarms spray tokens with no governance or recall.

PradySovereign closes all three. The Causality layer assigns counterfactual
credit ("what if I hadn't done X?"). The Critic vets every proposal before
execution. The Sovereign gate — enforced in code, not convention — approves
strategic direction. Every action is logged, attributable, and reversible.

## Quickstart

Requires Python 3.10+ and pip. No API keys, no LLM dependency for examples.

```bash
git clone https://github.com/prady4the4bady/PradyOS-S
cd PradyOS-S
pip install -e .

# Hello world: skill engine (learn -> run -> reinforce -> match)
python examples/hello_skill.py

# Dev swarm: 6-role multi-agent bugfix simulation
python examples/swarm_bugfix.py

# Dev swarm on this repo: codemap + architecture analysis
python examples/swarm_on_repo.py --task "Find one small improvement in this repo and propose a patch."
```

The last command runs a guild of 6 agents (planner, researcher, engineer,
analyst, critic, synthesizer) against the real codebase — 430+ modules,
72k LOC — via live AST introspection. It prints a structured analysis
without making a single network call.

## Modes

| Mode | What it does | Docs |
|------|-------------|------|
| Dev Swarm | Rapid prototyping with SkillEngine, GuildSwarm, SovereignClient facades | [docs/DEV_MODE.md](docs/DEV_MODE.md) |
| Local Personal | Governed daemon with personal_assistant blueprint | [docs/LOCAL_MODE.md](docs/LOCAL_MODE.md) |
| Enterprise | Docker compose + metrics + blueprint-driven fleet deployment | [docs/ENTERPRISE_MODE.md](docs/ENTERPRISE_MODE.md) |

## Pricing & Monetization

PradySovereign is free and open-source. Pro/Sovereign/Enterprise tiers unlock
advanced governance, audit, and fleet features. See the [pricing page](/billing)
and [docs/MONETIZATION.md](docs/MONETIZATION.md) for details.

## Commands

See [docs/COMMANDS.md](docs/COMMANDS.md) for a full reference covering install,
all modes, testing, benchmarks, billing, and the codemap.

## Benchmarks & Testing

8 internal throughput benchmarks (BloomFilter, MinHash, HyperLogLog,
CountSketch, TDigest, NoveltyDetector, AnalogyEngine, CompressionController)
run with a fixed seed for cross-machine reproducibility. All pass on HEAD.

```bash
python scripts/benchmarks.py --json
python scripts/prove.py --benchmark
python scripts/prove.py
```

- [docs/BENCHMARKS.md](docs/BENCHMARKS.md) — benchmark details and thresholds.
- [docs/TESTING.md](docs/TESTING.md) — test layout, known flakes, contributor guide.

## Architecture & Codemap

The system is structured in six autonomy layers over a probabilistic core, with
a multi-agent guild, self-healing loop, and structural self-knowledge via AST
introspection.

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — full technical architecture.
- [docs/CODEMAP.md](docs/CODEMAP.md) — how the agent introspects its own source tree.

## Project info

- **Code package**: `pradyos`
- **Public name**: PradySovereign
- **GitHub repo**: `PradyOS-S` (rename to `PradySovereign` planned)
- **License**: See `LICENSE`
