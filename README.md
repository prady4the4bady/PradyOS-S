# PradySovereign

**A governed, self‑improving cognitive layer for autonomous agents.**

PradySovereign is a high-autonomy agent runtime that combines a governed orchestration kernel with a deep cognitive substrate. It enables agents to operate with administrator-level authority while remaining strictly accountable to a human **Sovereign** who approves strategic direction.

## Why PradySovereign?

While other frameworks focus on swarm coordination or persistent memory, PradySovereign emphasizes **deeper cognition + governance**.

- **vs Hermes**: More robust cognitive substrate for internal reflection.
- **vs Ruflo**: Adds causal/cognitive layers to multi-agent swarms.
- **vs OpenClaw/NemoClaw**: Stronger internal cognition for self-improvement.

## Quickstart

Get the cognitive layer running locally in seconds:

```bash
git clone https://github.com/prady4thebady/PradyOS-S
cd PradyOS-S
pip install -e .
python scripts/demo_cognitive_layer.py
```

To explore the API and Governance Chamber:
```bash
python -m pradyos.sovereign_web
# Open http://localhost:8000/docs for API reference
```

### Hello World (Dev Mode)

```bash
python examples/hello_skill.py
python examples/swarm_bugfix.py
```

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
- [Agent Guidelines](CLAUDE.md)
- [Cognitive Demo](scripts/demo_cognitive_layer.py)
- [Dev Mode](docs/DEV_MODE.md)
- [Local Mode](docs/LOCAL_MODE.md)
- [Enterprise Mode](docs/ENTERPRISE_MODE.md)
- [Personal Assistant Demo](scripts/demo_personal_assistant.py)
- [Enterprise Deployment Demo](scripts/demo_enterprise_deployment.py)
