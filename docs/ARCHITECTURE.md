# PradySovereign Architecture

This document provides a detailed technical overview of the PradySovereign cognitive layer and agent runtime.

## Core Components

| Component | Role | Plane |
|-----------|------|-------|
| `pradyos.titan_ops` | Hidden command runner — admin-grade execution fabric | Execution |
| `pradyos.warden_grid` | Real-time health telemetry and incident detection | Recovery / Substrate |
| `pradyos.imperium` | Task queue, state machine, policy classifier, DAG | Orchestration |
| `pradyos.aurora_throne` | Sovereign Governance Chamber (terminal UI) | Experience |
| `pradyos.core` | Shared substrate — audit log, constitution, bus, IDs | Foundational |
| `pradyos.oracle` | AI reasoning, planning, autonomous proposal loop | Intelligence |
| `pradyos.campaign` | Campaign engine — multi-step DAG execution | Orchestration |
| `pradyos.proving_ground` | Constitutional admission gate | Safety |
| `pradyos.memory_citadel` | Persistent vector memory | Memory |
| `pradyos.sovereign` | Sovereign Web UI + CLI + REPL | Experience |
| `pradyos.guild` | Multi-agent organization (specialist roles, blackboard) + continual memory | Intelligence |
| `pradyos.skills` | Skill library — learn / match / reinforce / prune from experience | Learning |
| `pradyos.foresight` | Predict → deliberate → observe → learn (metacognition); optional LLM world-model | Autonomy (L1/L2) |
| `pradyos.drive` | Goal/drive manager — self-direction, **Sovereign-gated** | Autonomy (L3) |
| `pradyos.critic` | Adversarial critic ensemble (safety/correctness/value); optional LLM critic | Autonomy / Safety (L4) |
| `pradyos.causality` | Counterfactual credit assignment (cause vs. bystander) | Autonomy (L5) |
| `pradyos.reverie` | Idle cognition loop — reflection + curiosity (the "mind" ouroboros) | Autonomy |
| `pradyos.ascent` | Self-improvement loop + autonomous driver (the "code" ouroboros) | Autonomy |
| `pradyos.licensing` | Signed offline licenses, tiered entitlements, Stripe billing, open-mode | Monetization |
| `pradyos.core.llm` | Pluggable model provider (local Ollama → NVIDIA NIM / OpenAI-compatible) | Foundational |
| `pradyos.web.console` | Sovereign Command Console (glassmorphic OS shell served at `/`) | Experience |
| `pradyos.web.system_web` | Real OS telemetry + filesystem for the shell | Experience |

## Autonomy Stack (L1–L6)

The system is engineered in measurable layers of progressively more general, self-directed autonomy.

| Layer | Plane | What it adds | Status |
|------:|-------|--------------|:------:|
| **L1** | `skills` + planner | accumulate & reuse competence | ✅ |
| **L2** | `foresight` | predict an action's value; semantic prediction for novel states | ✅ |
| **L3** | `drive` | self-proposed goals, approved by the Sovereign before any action | ✅ |
| **L4** | `critic` | adversarial veto on dangerous/low-quality proposals | ✅ |
| **L5** | `causality` | counterfactual credit assignment ("what if I hadn't?") | ✅ |
| **L6** | `reverie` + consolidation | LLM-written curiosity goals + insight consolidation | ✅ |

### The Cognitive Loop
**perceive → plan → predict → act → compare → reflect → distill → self-direct → vet → attribute cause → improve code**

## Monetization & Security

### Licensing & AEGIS
- **Tiered licensing**: Signed, offline Ed25519 licenses (Free / Pro / Sovereign / Enterprise).
- **AEGIS integrity**: Signed Ed25519 manifest of source files. Tamper-evidence triggers a drop to the free tier.
- **Boot-level hardening**: Verified boot chain (Secure Boot signing, MOK, TPM2 sealing).

## Build Instructions (Internal)

### Local development
```bash
git clone <repo> pradyos
cd pradyos
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

### Docker dev environment
```bash
docker compose up --build
```

### Systemd deployment
```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pradyos-titan.service \
                            pradyos-warden.service \
                            pradyos-imperium.service
```

## Repository Layout
```
pradyos/
├── core/            # shared substrate (bus, audit, constitution, llm provider)
├── titan_ops/       # hidden command runner (Plane 2)
├── warden_grid/     # health telemetry + incident mesh (Plane 1/9)
├── imperium/        # orchestration kernel (Plane 3)
├── aurora_throne/   # governance terminal (Plane 10)
├── oracle/          # planning + autonomous proposal loop
├── guild/           # multi-agent organization + continual memory + auto-distill
├── skills/          # skill library (learn/match/reinforce)
├── foresight/       # L1/L2 metacognition (+ LLM world-model)
├── drive/           # L3 goal/drive manager (Sovereign-gated)
├── critic/           # L4 adversarial critic ensemble (+ LLM critic)
├── causality/       # L5 counterfactual credit assignment
├── reverie/         # idle cognition loop (+ background driver)
├── ascent/          # self-improvement loop (+ background driver)
├── licensing/       # signed licenses + tiers + Stripe billing + open-mode
└── web/             # FastAPI route modules incl. console (the OS shell)
docs/                # architecture, API contracts, AGI_ASI_ROADMAP
deploy/              # systemd units + Dockerfile
scripts/             # build/ISO/VM/install tooling
tests/               # pytest suite
var/                 # audit log + checkpoint state (gitignored)
```

## Phase History
(Retained for provenance)

- **Phase 0-7**: Core substrate, Governance, and Autonomy L1-L6 wired.
- **Phase 8**: ORACLE autonomous proposal loop.
- **Phase 9**: Hardened systemd units and Docker images.
- **Phase 10**: Redis inter-process bus.
- **Phase 11**: Autonomous self-healing.
- **Phase 16-21**: Telemetry, Memory Graph, Ledger, Intent Engine, Audit UI, and Hot-Reload.
- **Phase 22-27**: Metrics, Rate-Limiting, Health Scorecard, Audit Replay, Plugin Sandbox, and Bus Inspector.
- **Phase 28-36**: Decision Journal, Capability Registry, Watchpoints, Signal Aggregator, Snapshot Store, Correlation Engine, Integration Bus, Reactor, and State Manager.
- **Phase 37**: Self-Healing Monitor.
- **Phase 46-51**: Cognitive Layer (SemanticMemory, AttentionSketch, ExperienceDistribution, NoveltyDetector, AnalogyEngine, CompressionController).
