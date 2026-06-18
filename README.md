# PradySovereign

**A governed, self‑improving cognitive layer for autonomous agents.**

PradySovereign is a governed agent runtime with a probabilistic cognitive substrate — think memory, attention, novelty, analogy, and compression primitives — wired into a multi-agent guild that can introspect and improve its own codebase.

## Quickstart

```bash
git clone https://github.com/prady4the4bady/PradyOS-S
cd PradyOS-S
pip install -e .
python examples/hello_skill.py
python examples/swarm_bugfix.py
python examples/swarm_on_repo.py --task "Find one small improvement in this repo and propose a patch."
```

The swarm example introspects the actual repo via the codemap — 432 modules, 72k LOC — and produces a multi-role analysis without any LLM dependency.

## Key Concepts

### Autonomy Layers (L1–L6)
- **L1: Competence** — Skill accumulation and reuse.
- **L2: Foresight** — Predicting action value and novel states.
- **L3: Drive** — Self-proposed goals (Sovereign-gated).
- **L4: Critic** — Adversarial veto on dangerous proposals.
- **L5: Causality** — Counterfactual credit assignment.
- **L6: Reverie** — Idle reflection and insight consolidation.

### Cognitive Primitives
- **SemanticMemory**: Associative recall via MinHash/SimHash.
- **AttentionSketch**: Frequency-aware focus via Count-Sketch.
- **ExperienceDistribution**: Percentile-based anomaly detection.
- **NoveltyDetector**: Bloom/HLL-based surprise scoring.
- **AnalogyEngine**: Relational pattern matching.
- **CompressionController**: Strategy-based stream summarisation.

### The Self-Healing Loop
```text
  [ Perceive ] → [ Plan ] → [ Act ]
       ↑                         ↓
  [ Self-Direct ] ← [ Reflect ] ← [ Compare ]
       ↑                         ↓
  [ Improve Code ] ← [ Distill ] ← [ Attribute Cause ]
```

## Modes
- **Dev Swarm Mode**: Rapid prototyping with multi-agent guilds.
- **Local Personal Mode**: Governed personal assistant with local tool access.
- **Enterprise Mode**: Hardened, blueprint-driven deployment with full auditability.

## Links
- [Technical Architecture](docs/ARCHITECTURE.md)
- [Codemap — structural self-knowledge](docs/CODEMAP.md)
- [Benchmarks](docs/BENCHMARKS.md)
- [Dev Mode](docs/DEV_MODE.md)
- [Local Mode](docs/LOCAL_MODE.md)
- [Enterprise Mode](docs/ENTERPRISE_MODE.md)
