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

## 4b. The two ouroboros loops (background "thinking")

PradyOS runs two self-referential background loops — the OS continually turns on
itself to improve:

1. **ASCENT driver (code loop).** A heartbeat (`pradyos/ascent/driver.py`,
   default 300 s, wired in `sovereign_web.main`) reads the OS's *own source* in
   rotating batches and queues self-hardening proposals for Sovereign approval —
   read-only, bounded, crash-proof. This is the literal code ouroboros.
2. **REVERIE (cognition loop).** A new pass (`pradyos/reverie/`) reflects on the
   OS's *own thinking*: FORESIGHT calibration + the skill library → its biggest
   **blind spot** (most-surprising action) and weakest skill → a self-proposed
   **curiosity goal** (intrinsic motivation). Surfaced at `/api/v1/reverie/*`.

Together: ASCENT improves the *machinery*, REVERIE improves the *mind*. Both only
*propose* — the Sovereign still approves.

## 5. Status

- ✅ Shipped: perception, planning, guild, pluggable model, self-heal, memory,
  **ASCENT** code-ouroboros, **FORESIGHT** metacognition, the **skill library**,
  the **L1 planner bridge** (`/api/v1/plan`), **L1 auto-distillation** (completed
  Guild project → reusable skill / reinforce), and **REVERIE** (cognition loop).
- ✅ **L2 LLM world-model** (`foresight/llm_model.py`) — semantic, prior-anchored,
  fail-soft prediction via the pluggable model; opt-in via `PRADYOS_FORESIGHT_LLM`.
- ✅ **ReverieDriver** (`reverie/driver.py`) — the cognition heartbeat now runs
  unattended in production (`PRADYOS_REVERIE_INTERVAL`, default 240s), beside ASCENT.
- ✅ **L3 goal/drive manager** (`pradyos/drive/`) — REVERIE proposes curiosity
  goals → the Sovereign approves (the gate) → an approved goal runs through the
  Guild. The OS never acts on an unapproved goal. `/api/v1/drive/*`. This closes
  the loop: the OS now pursues what it's curious about, with your approval.
- ✅ **L4 critic ensemble** (`pradyos/critic/`) — skeptical critics score a
  proposal on safety/correctness/value; any safety blocker is a veto. Gates DRIVE:
  a dangerous goal can't run even after Sovereign approval. `/api/v1/critic/*`.
- ✅ **L5 causal reasoning** (`pradyos/causality/`) — counterfactual credit
  assignment: P(effect|cause) − P(effect|¬cause) tells a real cause from a
  bystander and answers "what if I hadn't done X?". `/api/v1/causality/*`.
- ✅ **LLM-backed critic** (`critic/llm_critic.py`) — a holistic, fail-soft judge
  added to the L4 panel when `PRADYOS_CRITIC_LLM` is set; catches risks the
  regexes miss without ever vetoing on model unavailability.
- 🎯 **The five-layer roadmap (L1–L5) is complete.**
- ✅ **Cross-plane integration wired**: FORESIGHT outcomes auto-feed CAUSALITY
  (action→success trials); the planner (`/api/v1/plan`) re-weights matched skills
  by causal strength; the console surfaces the loop (REVERIE insights + DRIVE
  goals with approve/run). Repo organized (legacy phase patches archived).
- ✅ **L6**: LLM-backed REVERIE reflector (`reverie/llm_reflector.py`, opt-in
  `PRADYOS_REVERIE_LLM`, fail-soft) + memory **consolidation** of insights
  (`/api/v1/reverie/consolidate` → dominant focus + standing directive).
- ✅ **Security (application layer): AEGIS** (`pradyos/aegis/`) — a signed Ed25519
  manifest of the OS's own files, verified at runtime; on tamper it drops to the
  free tier (tamper-EVIDENT) and **never harms the machine**. Vendor tool
  `scripts/build_manifest.py`; `/api/v1/aegis/verify`.
- ✅ **Boot-level hardening** (`scripts/harden_boot.sh` + `pradyos-aegis.service` +
  `python -m pradyos.aegis verify`): a verified boot chain — Secure Boot signing
  of kernel + GRUB, MOK enrollment, a locked bootloader, and optional TPM2 sealing
  to the measured boot state (PCRs 0,2,4,7). The AEGIS check runs at boot and
  extends the chain of trust into the PradyOS payload. Guarded/idempotent (skips
  cleanly when a tool or the TPM is absent). Design: [`docs/BOOT_HARDENING.md`].
- 🎯 **The roadmap is complete** (autonomy L1–L6 + cross-plane integration + the
  full security chain, application + boot). Further work is iteration, not new
  layers: an LLM-backed REVERIE driver tuning, deeper causal fusion, field hardening.
- Tests: foresight (+llm), plan, guild-distill, reverie (+driver/+l6), drive,
  critic (+llm), causality, aegis (+cli) — the full loop end-to-end.

*References are named for traceability only; no external text is reproduced here.*
