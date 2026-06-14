# PradyOS — Autonomy / AGI / ASI Roadmap

> **Honest framing.** PradyOS is an *autonomous operating system*: software that
> plans, acts, checks itself, and improves. "AGI/ASI" here means **progressively
> more general and self-directed autonomy**, engineered in measurable layers —
> not a claim of human-level or superhuman general intelligence. Every layer is
> deterministic where it can be, injected/testable, and gated by the Sovereign
> (you approve; the machine executes). Capability and **oversight** advance
> together — that is a hard design rule, not an afterthought.

This document maps what exists today, the layer just added (FORESIGHT), and the
researched next steps with the prior art each draws on.

---

## 1. The autonomy stack today

| Plane | Module | Role in the cognitive loop |
|------|--------|----------------------------|
| **Perception / state** | `warden_grid`, `sentinel_watch`, `system_web` | Read the machine + environment (CPU/RAM/disk/net, anomalies). |
| **Planning** | `oracle` | Turn an objective into an ordered plan of steps. |
| **Multi-agent execution** | `guild` | A team of specialist agents (now VEGA…ARES) that act using OS tools, with continual learning of past work. |
| **Model brain (pluggable)** | `core/llm` | One switch from local Ollama → NVIDIA NIM (Llama-70B / Nemotron / MiniMax-M3) → any OpenAI-compatible model. |
| **Self-healing** | `imperium` (SelfHealEngine) | Detect failed tasks, quarantine, retry, dead-letter. |
| **Memory** | `memory_citadel`, `memory_feedback` | Durable recall of plans, outcomes, feedback. |
| **Self-improvement** | `ascent` (driver + apply-gate) | Propose edits to PradyOS itself; the Sovereign approves; staged edits apply. |
| **Metacognition (NEW)** | `foresight` | Predict an action's value, choose, then compare prediction vs. reality and learn from the error. |
| **Governance / monetization** | `licensing`, `bastion`, `fortify` | Signed offline tiers; entitlement gating; integrity. |

The loop closes: **perceive → plan → predict → act → compare → reflect →
remember → improve.** FORESIGHT is the piece that was missing — the system can
now be *wrong on purpose-checked* and get measurably better-calibrated over time.

---

## 2. What FORESIGHT (this layer) adds, concretely

`pradyos/foresight/engine.py` implements the **Reflexion** pattern (Shinn et al.,
2023) fused with a lightweight **world-model** (Ha & Schmidhuber, 2018):

- **Predict** a 0–1 utility + confidence for each candidate action, blending a
  prior built from past episodes (experience sharpens foresight).
- **Deliberate**: rank actions by `value − risk·(1−confidence)`; pick the best.
- **Observe** the realised outcome; **surprise = |predicted − actual|**.
- **Reflect**: derive a short lesson; future predictions shift toward reality;
  mean surprise (calibration) provably drops (covered by `test_foresight.py`).

Endpoints: `/api/v1/foresight/{deliberate,observe,recall,stats,history,reset}`.
It is injected-predictor-ready, so the heuristic can later be swapped for an
LLM-backed estimator without touching callers.

---

## 3. Researched next layers (in recommended order)

Each entry: **what**, **why it raises autonomy**, **prior art**, **rough scope**.

### L1 — Skill Library  ✅ ALREADY EXISTS — integrated this round
- **Status.** A full skill library already ships as **`pradyos/skills`**
  (`/api/v1/skills/*`): `learn` (id/name/trigger/steps), `match` (intent
  retrieval), `reinforce` (success→confidence), `revise`, `prune`, `recall`,
  `stats`. Building a second one (`skillforge`) was started, found to **duplicate**
  this, and removed — per the OS's no-duplicates rule.
- **What was added instead — the bridge.** `POST /api/v1/plan`: match learned
  skills to an intent (skill library) → **deliberate** over them with FORESIGHT
  (predicted value × proven confidence) → return the chosen skill + its steps.
  Two existing planes now plan together; no new store.
- **Why.** Turns the dormant skill library into an actual decision: experience
  (skills) + foresight (calibration) jointly pick the next move.
- **Prior art.** Voyager (Wang et al., 2023); Generative Agents (Park et al., 2023).
- **Next within L1.** Auto-*distillation*: hook the Guild so a solved task writes a
  new skill automatically, and an outcome calls `skills.reinforce`. Medium.

### L2 — LLM-backed World Model for FORESIGHT
- **What.** Replace the heuristic predictor with the pluggable LLM (cheap local
  model) producing structured value/confidence; keep the heuristic as fallback.
- **Why.** Generalises foresight to unseen states (semantic, not just frequentist).
- **Prior art.** Reasoning-via-planning, Tree-of-Thoughts (Yao et al., 2023).
- **Scope.** A `predictor` adapter in `core/llm` + JSON schema. Small–medium.

### L3 — Goal/Drive Manager (self-directed objectives)
- **What.** A standing set of Sovereign-approved goals + a scheduler that lets the
  OS propose its own sub-goals during idle time (still gated by apply-gate).
- **Why.** The step from "does what it's told" → "pursues standing intent safely".
- **Prior art.** BabyAGI/AutoGPT task loops; intrinsic-motivation RL.
- **Scope.** Extend `ascent` + `campaign/scheduler`. Medium.

### L4 — Self-evaluation & critic ensemble
- **What.** Before the apply-gate, an adversarial critic panel scores proposed
  self-edits for correctness/safety; low scores are rejected automatically.
- **Why.** Higher-quality self-improvement without more human review load.
- **Prior art.** Constitutional AI (Bai et al., 2022); debate/critic models.
- **Scope.** New critic in `review` + `ascent`. Medium.

### L5 — Causal/counterfactual reasoning over the event bus
- **What.** Learn cause→effect links from `imperium` bus history; ask "what if I
  had not done X?" to attribute outcomes.
- **Why.** Stronger credit assignment → faster, safer learning than correlation.
- **Prior art.** Structural causal models (Pearl); model-based RL.
- **Scope.** New `pradyos/causality` plane consuming the bus. Larger.

---

## 4. Safety & oversight (advances with every layer — non-negotiable)

- **Sovereign-in-the-loop by default.** Autonomous self-edits stay behind the
  `ascent` apply-gate; the Sovereign approves before anything lands.
- **Tamper-EVIDENT, never tamper-punishing.** Integrity failures drop features /
  refuse to run — the OS **never harms the inspecting machine** (see
  `licensing/vault.py`). Anti-reverse-engineering is done with code signing,
  obfuscation, Secure Boot / TPM-sealed keys and self-disable — *not* retaliation.
- **Calibration as a guardrail.** FORESIGHT's mean-surprise is a live trust
  signal: a poorly-calibrated model should *lower* its own autonomy, not raise it.
- **Capability ⇒ oversight coupling.** No new autonomy layer ships without its
  matching check (critic, gate, or audit trail).

---

## 5. Status

- ✅ Shipped: perception, planning, guild, pluggable model, self-heal, memory,
  ascent self-improvement, **FORESIGHT metacognition**, the **skill library**
  (`pradyos/skills`), and the **L1 planner bridge** (`/api/v1/plan`) joining them.
- ▶️ Next: **L1 auto-distillation** (Guild success → new skill + reinforce), then
  **L2 LLM world-model** for FORESIGHT.
- Tests: `test_foresight.py` (13) proves the predict/learn loop calibrates;
  `test_plan_integration.py` proves skill-match + foresight pick the best move.

*References are named for traceability only; no external text is reproduced here.*
