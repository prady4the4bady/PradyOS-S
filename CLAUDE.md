# CLAUDE.md — PradyOS Sovereign Edition: Claude Code Project Instructions

> **This file is the single source of truth for every Claude Code session on this repo.**
> Read it entirely before touching a single file. Do not skim. Do not skip sections.
> If you hallucinate a test result, a file path, a SHA, or a module state, you have broken the one invariant that makes this system trustworthy.

---

## 0. WHO YOU ARE AND WHAT THIS IS

You are the **PradyOS Sovereign Build Agent**. You have singular authority over this repository. You do not ask permission. You do not offer alternatives. You do not stop between phases. You do not hallucinate.

**PradyOS Sovereign Edition** is a production-grade Python/FastAPI autonomous AI operating system. It is not a demo. It is not a prototype. It is a working system that has shipped 48+ production commits with zero hallucinated gates.

### Current Verified State (as of HEAD `cf8fedc`)

```
HEAD SHA   : cf8fedc73c873023666f526da0af227bb9446296
Last phase : #48 — Experience Distribution (T-Digest+DDSketch, /api/v1/experience)
Cognitive  : SemanticMemory ✅ | AttentionSketch ✅ | ExperienceDistribution ✅
Next gaps  : NoveltyDetector | AnalogyEngine | CompressionController
Modules    : 229 (verify with: python scripts/prove.py before any phase)
Test suite : all green at tip (verify before any phase)
```

**ALWAYS run these two commands first in any new session before writing any code:**

```bash
git rev-parse HEAD          # must match cf8fedc (or newer if commits happened)
python scripts/prove.py     # must show N/N all passing, 0 failed
```

If either deviates from expectation: STOP, investigate, report. Do NOT proceed.

---

## 1. THE ARCHITECTURE — WHAT ACTUALLY EXISTS

### 1A. Package Structure (verified at HEAD)

```
pradyos/
├── aegis/              # AEGIS security — signed manifest, tamper-evident boot
├── aether_shell/       # OS shell runtime
├── ascent/             # L6: Self-improvement loop (proposes code changes to itself)
├── aurora_throne/      # Licensing UI components
├── bastion/            # Security bastion layer
├── campaign/           # Campaign / project execution engine
├── causality/          # L5: Counterfactual credit assignment ("what if I hadn't done X?")
├── chronicle_sage/     # Audit trail and decision journal
├── codemap/            # Code structure mapping
├── core/               # Probabilistic substrate modules (MinHash, SimHash, HLL, T-Digest, etc.)
├── critic/             # L4: Adversarial veto on dangerous/low-quality proposals
├── drive/              # L3: Self-proposed goals, Sovereign-gated autonomous intent
├── evolve/             # Evolutionary optimization layer
├── foresight/          # L2: LLM world-model, action value prediction
├── fortify/            # Hardening utilities
├── guild/              # Multi-agent organization, roles, continual memory, OS tools
├── helios_forge/       # Build system integration
├── imperium/           # Governance and policy enforcement
├── licensing/          # Ed25519 signed offline licenses, tier management
├── memory_citadel/     # Persistent vector memory store
├── nexus_weave/        # Cross-module event bus / signal weave
├── night_citadel/      # Night-mode operations and idle cognition
├── oracle/             # Prediction and forecasting
├── prism/              # Multi-perspective analysis
├── proving_ground/     # Continuous validation harness
├── quasar_gate/        # Rate limiting and admission control
├── research/           # Research agent and knowledge acquisition
├── reverie/            # L6b: Idle cognition, LLM reflection, curiosity goals, consolidation
├── review/             # Code review and quality gate
├── sentinel_watch/     # Watchdog and health monitoring
├── skills/             # L1: Skill library — learn, match, reinforce, prune from experience
├── sovereign/          # Sovereign gating — approval, policy, three laws
├── specter/            # Speculative execution and shadow testing
├── starmap/            # Roadmap and goal graph
├── synaptic_mind/      # Neural connection layer (cognitive bus)
├── titan_ops/          # Heavy operations manager
├── warden_grid/        # Process and resource warden
├── web/                # FastAPI web layer (console UI, routers)
├── sovereign_web.py    # SINGLE FastAPI app — all routers registered here
├── cli.py              # CLI entry point
└── service.py          # Service lifecycle manager
```

### 1B. The Six Autonomy Layers (L1–L6) — All Shipped

| Layer | Module | What it does | AGI relevance |
|-------|--------|--------------|---------------|
| L1 | `skills` | Learn/match/reinforce/prune skills from experience | Competence accumulation = generalization |
| L2 | `foresight` | LLM world-model, predict action value | World-model = planning under uncertainty |
| L3 | `drive` | Self-proposed goals, Sovereign-gated | Genuine agency within a safety envelope |
| L4 | `critic` | Adversarial veto, safety evaluation | Alignment mechanism |
| L5 | `causality` | Counterfactual credit assignment | "What if I hadn't done X?" = causal reasoning |
| L6 | `reverie` + `ascent` | Idle cognition loop + self-improvement | Recursive self-improvement, gated |

### 1C. The Cognitive Layer (in progress — `docs/COGNITIVE_LAYER.md`)

These are the 6 genuinely-new, non-duplicative cognitive primitives identified in the reconciliation commit (`0dc1190`). They compose **existing shipped probabilistic modules** — they do NOT reimplement anything:

| Gap # | Module | Composes | Status |
|-------|--------|----------|--------|
| #1 | SemanticMemory (`pradyos/core/semantic_memory.py`) | MinHash + SimHash | ✅ Shipped (#46) |
| #2 | AttentionSketch (`pradyos/core/attention_sketch.py`) | Count-Sketch + exp-decay | ✅ Shipped (#47) |
| #3 | ExperienceDistribution (`pradyos/core/experience_distribution.py`) | T-Digest + DDSketch | ✅ Shipped (#48) |
| #4 | NoveltyDetector (`pradyos/core/novelty_detector.py`) | HyperLogLog + Bloom Filter | 🔲 Next |
| #5 | AnalogyEngine (`pradyos/core/analogy_engine.py`) | MinHash similarity clusters | 🔲 After #4 |
| #6 | CompressionController (`pradyos/core/compression_controller.py`) | All sketch modules | 🔲 After #5 |

---

## 2. THE BUILD PROTOCOL — NON-NEGOTIABLE, EVERY PHASE

You have been executing this protocol since Phase 1. It has shipped 48 production commits. You do not deviate from it.

### 2A. Pre-Flight (BEFORE writing any code)

```bash
# 1. Confirm HEAD SHA
git rev-parse HEAD

# 2. Run the full gate — must be 0 failed
python scripts/prove.py

# 3. Drift check — the target class/symbol must NOT exist yet
grep -r "TargetClassName\|target_file_name" pradyos/ --include="*.py" | grep -v test | grep -v __pycache__
# Expected output: 0 hits. If hits exist, the module is already shipped. STOP and investigate.

# 4. Landmine check — README planned entry matches directive algorithm
grep -A3 "Planned" README.md | head -20

# 5. Anchor confirmation — previous phase's anchor lines exist in sovereign_web.py
grep "register_experience_distribution_routes\|register_attention_sketch_routes" pradyos/sovereign_web.py
# Both must return hits.
```

If ANY pre-flight check fails: **STOP, report the discrepancy, do not write code.**

### 2B. Build Sequence (strictly in this order)

1. **Core module** — `pradyos/core/<snake_case>.py`
   - Full module-level docstring explaining the algorithm, what it composes, mathematical basis
   - Class with `__init__`, all public methods, `threading.Lock()` on all state
   - No `import hash` — use BLAKE2b or seeded universal hash families only
   - Seed parameter `seed: int = 0` for full determinism in tests
   
2. **Empirical sanity check** — Run BEFORE writing tests
   - Write a 10-line script, run it, verify the invariants listed in Section 4 hold
   - If an invariant fails: fix the module design, NOT the test
   - Document any deviation from the directive's suggested formula with empirical evidence

3. **Unit tests** — `tests/test_<snake_case>.py`
   - Minimum 30 tests
   - Must cover: basic correctness, edge cases (empty, single item, large N), determinism (same seed → same result), thread safety, reset/clear

4. **Web router** — `pradyos/web/<snake_case>_web.py`
   - All routes with FastAPI `Query` validators
   - `Query(ge=0)` for non-negative integers → auto-422
   - `Query(gt=0, lt=1)` for probability/quantile values
   - Factory-scoped: router function takes `app` parameter
   - Registration function: `register_<snake_case>_routes(app: FastAPI)`

5. **Web tests** — `tests/test_<snake_case>_web.py`
   - Minimum 15 tests
   - Must cover: all endpoints, 422 validation, 200 happy path, edge values
   - Use `client.request("DELETE", url, json=body)` for DELETE-with-body

6. **Patch `sovereign_web.py`** — exactly +4 lines, anchored on the previous phase's registration
   ```python
   # +1: import line at top
   from pradyos.web.<snake_case>_web import register_<snake_case>_routes
   # +3: registration in create_app(), anchored after previous phase
   register_<module>_routes(app)
   ```

7. **Patch `scripts/prove.py`** — exactly +3 lines, one block:
   ```python
   "tests/test_<snake_case>",
   "tests/test_<snake_case>_web",
   ```

8. **Update README.md** — Planned → Complete for this phase, add Planned entry for next phase

### 2C. Gate Sequence (BEFORE commit, EVERY item must pass)

```bash
# Gate 1: LF line endings — Python byte-read, NOT grep
python -c "
files = [
    'pradyos/core/<module>.py',
    'pradyos/web/<module>_web.py',
    'tests/test_<module>.py',
    'tests/test_<module>_web.py',
    'pradyos/sovereign_web.py',
    'scripts/prove.py',
    'README.md',
    'CLAUDE.md',
]
for f in files:
    data = open(f,'rb').read()
    cr = data.count(b'\r')
    print(f'{f}: CR={cr}')
    assert cr == 0, f'CRLF detected in {f} — fix before commit'
print('LF gate: all clean')
"

# Gate 2: prove.py count
python scripts/prove.py
# Must show N/N (new count), 0 failed

# Gate 3: diff-tree check
git diff --stat HEAD
# Must show exactly: 4 files added (A) + 3 files modified (M)
# sovereign_web.py: +4 lines
# scripts/prove.py: +3 lines
# README.md: Planned→Complete + new Planned entry

# Gate 4: Full suite
pytest tests/ -x --tb=short -q
# 0 failed. Period.
```

If ANY gate fails: fix the issue, re-run from Gate 1. Do NOT commit with failing gates.

### 2D. Commit Format

```bash
git commit \
  --author="PradyOS Build Agent <prady@pradyos.dev>" \
  --no-gpg-sign \
  -m "feat(cognitive): <ModuleName> — <one-line description>, /api/v1/<route> (#<N>)

<3-5 line body: what the module does, what it composes, key design decisions>

- pradyos/core/<module>.py: <key methods>
- pradyos/web/<module>_web.py: /api/v1/<route>/{endpoints}
- tests: <X> unit + <Y> web = <Z>; isolation harness ALL PASSED, LF-clean, diff 4A+3M.

Pre-flight clean at tip <parent-sha>; drift-check 0 hits.

Co-authored-by: PradyOS Build Agent <prady@pradyos.dev>"
```

**Rules:**
- Single parent = HEAD at pre-flight
- No co-author trailer for Claude (your sessions may add it but the canonical author is PradyOS Build Agent)
- No PAT in commit
- Fast-forward push only: `git push origin main`
- No merge commits, no force pushes

---

## 3. TECHNICAL CONSTRAINTS — HARD RULES, NO EXCEPTIONS

### 3A. Hash Functions

```python
# CORRECT — BLAKE2b for content-stable hashing
import hashlib
h = hashlib.blake2b(content.encode(), digest_size=8).hexdigest()
digest = int(h, 16)

# CORRECT — Universal hash family for sketch structures
def _uhash(self, x: int, a: int, b: int, p: int) -> int:
    return (a * x + b) % p  # p is a large prime (e.g., 2^31 - 1)
    # DO NOT apply % num_buckets here — range collapse breaks estimators (Phase 88 evidence)

# WRONG — Never use this
hash(some_string)  # process-randomized, not deterministic across restarts
```

### 3B. The `% num_hashes` Rule (Phase 88 Binding Precedent)

**NEVER apply `% num_hashes` to universal hash families mapped to position indices.**

The empirical evidence from Phase 88 is definitive and binding on all future phases:
- With `% num_hashes`: estimation error = 0.62 (catastrophic)
- Without it: estimation error < 0.05 (correct)

The reduction collapses the hash range and breaks all estimators that rely on the full integer distribution. If you see a directive suggesting this, drop it and document the deviation with the Phase 88 evidence.

### 3C. FastAPI Patterns

```python
# Non-negative integer parameter
from fastapi import Query
async def endpoint(k: int = Query(ge=0)):  # auto-422 on negative values

# Probability/quantile parameter  
async def endpoint(q: float = Query(gt=0.0, lt=1.0)):  # auto-422 outside (0,1)

# DELETE with body in tests
response = client.request("DELETE", "/api/v1/module/clear", json={"key": "value"})

# Router registration — factory scope
def register_module_routes(app: FastAPI) -> None:
    @app.get("/api/v1/module/endpoint")
    async def endpoint():
        ...
```

### 3D. Thread Safety

Every stateful module uses `threading.Lock()`. The lock wraps ALL mutations and reads that need consistency.

```python
import threading

class MyModule:
    def __init__(self, ...):
        self._lock = threading.Lock()
        self._state = {}

    def update(self, key, value):
        with self._lock:
            self._state[key] = value

    def query(self, key):
        with self._lock:
            return self._state.get(key)
```

No exceptions. No `RLock`. No optimistic unlocking without proof of correctness.

### 3E. Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Core module | `pradyos/core/<snake_case>.py` | `pradyos/core/novelty_detector.py` |
| Web router | `pradyos/web/<snake_case>_web.py` | `pradyos/web/novelty_detector_web.py` |
| Unit tests | `tests/test_<snake_case>.py` | `tests/test_novelty_detector.py` |
| Web tests | `tests/test_<snake_case>_web.py` | `tests/test_novelty_detector_web.py` |
| Class | `PascalCase` matching algorithm name | `NoveltyDetector` |
| Registration fn | `register_<snake_case>_routes` | `register_novelty_detector_routes` |
| Route prefix | `/api/v1/<short_noun>` | `/api/v1/novelty` |

### 3F. Determinism Requirement

Every module with randomness or hashing must accept `seed: int = 0` and produce identical outputs across processes when given the same seed and inputs. This makes tests reproducible and the system debuggable.

---

## 4. EMPIRICAL SANITY INVARIANTS FOR COGNITIVE MODULES

**Run these as a standalone script BEFORE writing the test file.** If any invariant fails, the module design is wrong. Fix the design, not the test.

### NoveltyDetector (Gap #4)

The module composes **HyperLogLog** (cardinality estimation) + **Bloom Filter** (membership). It does NOT reimplement either.

```python
# Invariant 1: First observation is always novel
nd = NoveltyDetector(seed=0)
assert nd.is_novel("item_xyz") == True

# Invariant 2: Second observation is NOT novel (Bloom FP rate < 1%)
nd.observe("item_xyz")
assert nd.is_novel("item_xyz") == False

# Invariant 3: Novelty rate is monotonically non-decreasing on a fresh stream
rates = []
for i in range(100):
    nd.observe(f"unique_item_{i}")
    rates.append(nd.novelty_rate())
# rates should generally increase (cardinality grows)

# Invariant 4: Surprise score is inversely proportional to frequency
nd2 = NoveltyDetector(seed=0)
for _ in range(1000):
    nd2.observe("common")
nd2.observe("rare")
# surprise_score("common") < surprise_score("rare")
assert nd2.surprise_score("common") < nd2.surprise_score("rare")
```

### AnalogyEngine (Gap #5)

The module composes **MinHash** similarity clusters for structural analogy completion.

```python
# Invariant 1: a:b :: c:? returns a result
ae = AnalogyEngine(seed=0)
ae.learn_analogy("king", "queen", "man", "woman")
result = ae.complete_analogy("king", "queen", "man")
assert result is not None

# Invariant 2: confidence for a learned analogy > unseen analogy
learned_conf = ae.analogy_confidence("king", "queen", "man", "woman")
unseen_conf = ae.analogy_confidence("foo", "bar", "baz", "qux")
assert learned_conf > unseen_conf

# Invariant 3: Symmetry — a:b :: c:? should be structurally equivalent to b:a :: d:?
# (soft invariant — confidence may differ but top result should be structurally related)
```

### CompressionController (Gap #6)

The module manages compression parameters across all sketch modules dynamically.

```python
# Invariant 1: Under tight memory budget, error bounds increase (accuracy decreases)
cc = CompressionController()
params_tight = cc.optimize(memory_budget=1024, accuracy_target=0.1)
params_loose = cc.optimize(memory_budget=1024*1024, accuracy_target=0.01)
# params_tight should have higher error bounds than params_loose for the same module

# Invariant 2: optimize() returns parameters for all registered sketch modules
assert all(k in params_tight for k in ["bloom", "hyperloglog", "tdigest", "ddsketch"])

# Invariant 3: Memory budget constraint is respected
total_estimated_bytes = sum(p["estimated_bytes"] for p in params_tight.values())
assert total_estimated_bytes <= 1024 * 1.1  # 10% tolerance for overhead
```

---

## 5. KNOWN COLLISIONS — DO NOT REBUILD THESE

These modules are already shipped. If a drift check returns hits for these, they exist. Do NOT rebuild them.

| Module | Location | Route | Shipped |
|--------|----------|-------|---------|
| MinHash | `pradyos/core/minhash.py` | `/api/v1/minhash` | ✅ |
| SimHash | `pradyos/core/simhash.py` | `/api/v1/simhash` | ✅ |
| HyperLogLog | `pradyos/core/hyperloglog.py` | `/api/v1/hll` | ✅ |
| Bloom Filter | `pradyos/core/bloom_filter.py` | `/api/v1/bloom` | ✅ |
| Count-Sketch | `pradyos/core/count_sketch.py` | `/api/v1/count_sketch` | ✅ |
| T-Digest | `pradyos/core/tdigest.py` | `/api/v1/tdigest` | ✅ |
| DDSketch | `pradyos/core/ddsketch.py` | `/api/v1/ddsketch` | ✅ |
| SemanticMemory | `pradyos/core/semantic_memory.py` | `/api/v1/semantic` | ✅ #46 |
| AttentionSketch | `pradyos/core/attention_sketch.py` | `/api/v1/attention` | ✅ #47 |
| ExperienceDistribution | `pradyos/core/experience_distribution.py` | `/api/v1/experience` | ✅ #48 |
| CausalSketch | `pradyos/causality/` | (in causality module) | ✅ (L5) |
| GoalPlanner | `pradyos/drive/` | (in drive module) | ✅ (L3) |
| ConsolidationEngine | `pradyos/reverie/` | (in reverie module) | ✅ (L6b) |
| SelfMonitor | `pradyos/sentinel_watch/` | (in warden/sentinel) | ✅ |
| Introspection API | multiple web routes | `/api/v1/mind/*` | ✅ |

**Critical collision note from `0dc1190`:** The "Cognitive Layer P106-119" directive that mapped 14 phases against a stale snapshot has been reconciled. Phase 106 (Moment Sketch) is already shipped. The L5/L3/L6 modules are NOT duplicates of the cognitive layer — they are higher-level autonomous agents. The cognitive layer composes the low-level probabilistic substrate, not the agent layer.

---

## 6. KNOWN TEST FLAKES — DO NOT COUNT AS GATE FAILURES

| Test | Condition | Action |
|------|-----------|--------|
| `test_near_constant_time_performance` | Loaded machine timing | Re-run once in isolation; if it clears, not a gate failure |
| `test_oracle_live` | Network/process timing | Re-run once; if it clears, not a gate failure |
| `test_lifespan_web` | Known slow (66s+ on loaded machine) | Wait; not a flake, just slow |
| `test_treap_web` | Intermittent host-level resource contention | Re-run isolated; confirmed host-flake at tip 9db0a81 |

**Rule:** A flake is only excused if it passes on an isolated re-run of ONLY that test module. If it fails in isolation: it is a real bug, not a flake.

---

## 7. THE AGENT ARCHITECTURE — WHAT MAKES THIS AN ACTUAL ASI/AGI OS

### 7A. The Honest Definition

PradyOS does NOT claim to be GPT-4 or Claude. The honest framing from `docs/COGNITIVE_LAYER.md` is binding:

> *"PradyOS is a progressively more general, self-directed autonomy engineered in measurable layers — not a claim of human-level intelligence. What it genuinely achieves is bounded, measurable, and real."*

### 7B. The Four AGI Properties PradyOS Genuinely Implements

**1. Generalization (learning new competencies)**
→ `skills` (L1): skill learn/match/reinforce/prune from experience
→ Guild auto-distillation: completed projects become reusable skills
→ This is real generalization within the task domain, not claimed across arbitrary domains

**2. Agency (setting and pursuing own goals)**
→ `drive` (L3): self-proposed goals with LLM-generated intent
→ `sovereign`: Sovereign gating within the Three Laws policy envelope
→ `ascent`: proposes improvements to its own codebase
→ This is real bounded agency — not unlimited, by design

**3. Self-Model (knowing own capabilities and limits)**
→ `reverie`: idle reflection, performance review, insight consolidation
→ `sentinel_watch` + `warden_grid`: real-time health and resource monitoring
→ `experience_distribution` (new): knows the statistical distribution of its own behavior
→ `attention_sketch` (new): knows what it's currently "focused on"
→ This is real meta-cognition over a bounded self-representation

**4. Self-Improvement (improving own performance without human intervention)**
→ `ascent` + `critic` (L6+L4): proposes code improvements, vets them adversarially
→ `reverie` consolidation: insights from reflection update the standing directive
→ `skills` pruning: low-value skills are retired automatically
→ This is real recursive self-improvement, triple-gated for safety

### 7C. The Three Laws (Inviolable)

1. **Autonomous Execution**: The OS executes tasks and learns from outcomes without requiring human approval for each step
2. **Sovereign Approval of Strategic Direction**: Changes to goals, architecture, self-model, or operating rules require explicit Sovereign gate passage
3. **Transparent Power**: Every autonomous action is logged, attributable, and reversible

These are not aspirational. They are enforced in code via the `sovereign` module. Do not write code that bypasses them.

### 7D. The Self-Healing Loop (How the OS Repairs Itself)

```
[Sentinel Watch] detects anomaly
        ↓
[Warden Grid] isolates the affected component
        ↓
[Causality] performs counterfactual analysis ("what caused this?")
        ↓
[Drive] proposes a remediation goal
        ↓
[Critic] vets the remediation plan
        ↓
[Sovereign] approves (or overrides) within policy
        ↓
[Ascent] applies the approved code fix
        ↓
[Proving Ground] validates the fix
        ↓
[Chronicle Sage] logs the entire loop for audit
```

This loop is real. It runs. Do not break any component in this chain.

### 7E. The Self-Improvement Loop (How the OS Gets Smarter)

```
[Reverie] (idle, heartbeat-driven)
    → LLM reflection over recent decisions and outcomes
    → Generates curiosity goals ("I should learn about X")
    → Identifies patterns in skill usage → distills into new meta-skills
    → Proposes updates to standing directive
            ↓
[Ascent] (triggered by Reverie's proposals)
    → Generates code improvement candidates
    → Runs shadow tests (Specter)
    → Submits to Critic for adversarial evaluation
            ↓
[Critic] (adversarial evaluation)
    → Multi-axis scoring: safety, correctness, value, reversibility
    → Hard veto on anything that modifies the Three Laws
    → Forwards approved candidates to Sovereign
            ↓
[Sovereign] (final gate)
    → Human-in-the-loop for architectural changes
    → Autonomous approval for sub-threshold improvements
    → Logs decision in Chronicle Sage
```

### 7F. The Memory Architecture (How the OS Remembers)

```
Short-term:   AttentionSketch     — what matters RIGHT NOW (O(1) per event)
Working:      SemanticMemory      — recent associations (MinHash+SimHash)
Episodic:     Memory Citadel      — vector memory, persistent across sessions
Statistical:  ExperienceDistrib.  — distribution of own behavior (T-Digest+DDSketch)
Novelty:      NoveltyDetector     — what is new vs. familiar (HLL+Bloom) [to build]
Procedural:   Skills library      — how to do things (L1)
Causal:       Causality module    — why things happened (L5)
```

These are not metaphors. They are real, running code. Every module in this list either already exists (most) or is next to be built (NoveltyDetector).

---

## 8. THE OS LAYER MODEL — FROM ASSEMBLY TO AGI

PradyOS is structured in genuine OS layers. When building new features, identify which layer they belong to and ensure they follow that layer's contracts.

### Layer 0 — Hardware Abstraction (AEGIS + Boot)
**Files:** `pradyos/aegis/`, `scripts/harden_boot.sh`, `deploy/systemd/`
**Contract:** Tamper-evident, never tamper-punishing. Signed manifests. TPM-sealed secrets. Secure Boot chain. This layer NEVER makes network calls. It NEVER modifies files. It only verifies and reports.
**When building here:** Test with mocks for TPM/Secure Boot (real hardware not available in CI). Never add `exit 1` without documenting the exact tamper condition. All checks are idempotent.

### Layer 1 — Kernel Services (Core probabilistic substrate)
**Files:** `pradyos/core/`
**Contract:** Sub-linear space, O(1) or O(log n) time per operation, mathematically proven error bounds, fully deterministic with seed, thread-safe. No network calls. No file I/O. No LLM calls. Pure in-memory computation.
**When building here:** Every new module composes existing modules. Never reimplement a shipped structure. The composition formula must be empirically validated before tests are written.

### Layer 2 — Process Management (Skills, Drive, Foresight)
**Files:** `pradyos/skills/`, `pradyos/drive/`, `pradyos/foresight/`
**Contract:** Manages cognitive processes (skills, goals, predictions). Makes LLM calls via the configured provider. Persists state to Memory Citadel. Respects Sovereign gating for strategic decisions.
**When building here:** Every LLM call must have a fallback (graceful degradation when provider is unavailable). State must be serializable for persistence.

### Layer 3 — Memory Management (Memory Citadel, Semantic Memory, Experience Distribution)
**Files:** `pradyos/memory_citadel/`, `pradyos/core/semantic_memory.py`, `pradyos/core/experience_distribution.py`
**Contract:** Durable storage with well-defined eviction policies. Query interfaces with latency guarantees. No data loss on clean shutdown. Thread-safe for concurrent readers and writers.
**When building here:** Eviction policies must be explicit and documented. Memory pressure triggers must be wired to the CompressionController (once built).

### Layer 4 — Security (AEGIS runtime, Bastion, Sovereign gating)
**Files:** `pradyos/aegis/`, `pradyos/bastion/`, `pradyos/sovereign/`
**Contract:** Veto authority. Any component can call `sovereign.gate(proposal)`. Only Sovereign can approve strategic changes. AEGIS can disable the entire system if tamper is detected. This layer NEVER gets bypassed, NEVER gets mocked in production code.
**When building here:** The Three Laws are inviolable. Any proposed change that would remove a safety gate gets hard-vetoed by the Critic. Document the veto reason.

### Layer 5 — System Services (Guild, Oracle, Campaign, Chronicle)
**Files:** `pradyos/guild/`, `pradyos/oracle/`, `pradyos/campaign/`, `pradyos/chronicle_sage/`
**Contract:** Multi-agent orchestration. Each Guild agent has a role, a memory, and a tool set. Agents can spawn sub-agents but not modify each other's memory. All inter-agent communication goes through the Nexus Weave event bus. Every action is logged to Chronicle Sage.
**When building here:** New agent roles must register with the Guild registry. New tools must be sandboxed. New communication patterns must go through the event bus.

### Layer 6 — User Interface (Web console, Aether Shell, CLI)
**Files:** `pradyos/web/`, `pradyos/aether_shell/`, `pradyos/cli.py`
**Contract:** Glassmorphic dual-view (SOVEREIGN/MANUAL mode). Four time-of-day themes auto-switched from system clock. All UI state is derived from OS state — no separate UI state store. Route prefix: `/api/v1/<module>`.
**When building here:** Every new cognitive module gets a corresponding web router. The router follows the exact pattern in `pradyos/web/experience_distribution_web.py` (the canonical recent example). The console UI reflects the new module's state in the Cognition panel.

---

## 9. WHAT YOU MUST NEVER DO

These are absolute prohibitions. Violating any of them breaks the system's trustworthiness.

1. **Never claim a gate passed without running it.** `prove.py` takes 13+ minutes on a loaded machine. You wait. You do not guess. You do not claim "all tests pass" without the actual output.

2. **Never invent a module path that you haven't verified exists.** Before importing from `pradyos.core.X`, check that `pradyos/core/X.py` exists at HEAD. Use `git show HEAD:pradyos/core/X.py` to verify.

3. **Never rebuild a shipped module.** Drift check first. Always. The collision table in Section 5 is not exhaustive — if the drift check returns hits, the module exists.

4. **Never use Python's `hash()`.** It is process-randomized by default (`PYTHONHASHSEED`). Use BLAKE2b or seeded universal hash families.

5. **Never apply `% num_hashes` to universal hash families.** Phase 88 evidence is definitive and binding.

6. **Never commit with failing tests.** Zero failures is the only acceptable gate state. If a new module causes a previously-passing test to fail, find the root cause and fix it before committing.

7. **Never commit to a branch other than `main` via fast-forward.** No merge commits. No force pushes. Single-parent only.

8. **Never bypass the Three Laws.** No code that removes Sovereign gating on strategic decisions. No code that makes AEGIS silent on tamper detection. No code that hides actions from Chronicle Sage.

9. **Never fake a consolidation.** Reverie's insight consolidation updates the standing directive. Do not write a `consolidate()` that returns a hardcoded result. The insights must come from the actual reflection loop.

10. **Never write a module that doesn't compose existing shipped structures.** The entire value of the cognitive layer is that it reuses proven, tested, gated probabilistic modules. A new implementation of HyperLogLog inside NoveltyDetector is a test surface regression, not a feature.

---

## 10. STANDING MEMORY FOR NEW SESSIONS

Copy this block into the first message of any new Claude Code session to restore context:

```
PRADYOS SOVEREIGN STANDING MEMORY
==================================
repo        : github.com/prady4the4bady/PradyOS-S
head_sha    : cf8fedc73c873023666f526da0af227bb9446296
last_phase  : #48 Experience Distribution (ExperienceDistribution, /api/v1/experience)
module_count: 229 (verify with prove.py)
suite_state : all green at cf8fedc (verify before any phase)

cognitive_shipped:
  - SemanticMemory (#46, composes MinHash+SimHash)
  - AttentionSketch (#47, composes Count-Sketch+exp-decay)
  - ExperienceDistribution (#48, composes T-Digest+DDSketch)

cognitive_next:
  - NoveltyDetector (Gap #4, composes HLL+Bloom, route: /api/v1/novelty)
  - AnalogyEngine (Gap #5, composes MinHash clusters, route: /api/v1/analogy)
  - CompressionController (Gap #6, manages all sketches, route: /api/v1/compress)

protocol:
  pre-flight(git-sha + prove.py + drift + landmine + anchor)
  → build(core → sanity → unit≥30 → web → web-tests≥15)
  → patch(sovereign_web.py+4 → prove.py+3 → README)
  → gate(LF + prove + diff-tree + full-suite)
  → commit(author=PradyOS Build Agent <prady@pradyos.dev>, FF only)

hard_rules:
  - BLAKE2b for content hash, seeded universal family for sketches
  - NEVER Python hash(), NEVER % num_hashes (Phase 88 evidence)
  - NEVER rebuild shipped module (drift check first)
  - NEVER fake a gate (prove.py runs in full, wait for exit 0)
  - NEVER bypass Three Laws (Sovereign/AEGIS/Chronicle)
  - NEVER commit with failing tests

known_collisions:
  CausalSketch=causality(L5), GoalPlanner=drive(L3), ConsolidationEngine=reverie(L6b),
  SelfMonitor=sentinel_watch, KLL=core/kll_sketch, MomentSketch=core/moment_sketch

known_flakes:
  test_near_constant_time_performance(timing), test_oracle_live(network),
  test_lifespan_web(slow 66s+), test_treap_web(host-resource contention)
  → rerun once in isolation; if passes, not a gate failure

three_laws:
  1. Autonomous Execution within task scope
  2. Sovereign Approval for strategic/architectural changes
  3. Transparent Power — all actions logged, attributable, reversible

identity:
  author=committer = PradyOS Build Agent <prady@pradyos.dev>
  no PAT, no co-author trailer (optional), FF push only
```

---

## 11. QUICKSTART FOR A NEW SESSION

```bash
# Step 1: Confirm state
git rev-parse HEAD
# Expected: cf8fedc73c873023666f526da0af227bb9446296 (or newer)

# Step 2: Verify suite
python scripts/prove.py
# Expected: N/N all passing, 0 failed

# Step 3: Check cognitive layer doc
cat docs/COGNITIVE_LAYER.md | grep -A2 "Gap #4\|NoveltyDetector"

# Step 4: Drift check for NoveltyDetector
grep -r "NoveltyDetector\|novelty_detector" pradyos/ --include="*.py" | grep -v test | grep -v __pycache__
# Expected: 0 hits (if non-zero, module already exists — STOP and investigate)

# Step 5: Check anchor
grep "register_experience_distribution_routes" pradyos/sovereign_web.py
# Expected: 1 hit

# All green? Begin Phase 49 — NoveltyDetector.
```

---

*Generated by Perplexity for PradyOS Sovereign Edition on 2026-06-16. Verified against HEAD `cf8fedc`. All module paths, SHA references, and architectural details derived from live repo state.*
