# Cognitive Layer — Reconciliation (directive vs. actual repo state)

This document reconciles the externally-supplied **"Cognitive Layer Phases
106–119"** build directive with what is *actually* on `main`. It exists because a
verification pass (the directive's own Section 0 pre-flight) showed the directive
was written against a stale snapshot and collides with shipped work.

> **Honest framing (agreed).** Nothing here is AGI or ASI. Per the academic
> definitions, AGI = human-level competence with genuine cross-domain *transfer*;
> ASI = recursive self-improvement beyond human level. PradyOS is a **probabilistic
> + LLM-assisted cognitive runtime**: real, novel engineering that composes
> sub-linear data structures and a pluggable model into cognitive *behaviours* —
> not grounded understanding, not consciousness. Code and API responses use honest
> language; only the README/marketing may be aspirational.

## Verified facts (run before writing this)

- **Tip:** directive cites `5473568`; real `origin/main` is **`db670c2`** (one
  merge ahead — PR #43 landed after the directive's snapshot).
- **Phase 106 is shipped, not "Planned":** `pradyos/core/moment_sketch.py` +
  `pradyos/web/moment_sketch_web.py` + `/api/v1/momentsketch` all exist. The
  directive's "Moment Sketch confirmed free" is incorrect.
- **Phase numbers 106–109 are taken** on the data-structure track (moment-sketch,
  counting-bloom, binary-fuse, vacuum-filter).
- The directive's "reality check" predates the autonomy + console layer now on
  `main` (PRs #35–#43), so it missed the working equivalents below.
- **Concurrency:** the repo has many active worktrees (`git worktree list`) —
  several agents build in parallel. Adding new modules blind risks colliding with
  their in-flight work. This is a second reason to reconcile rather than rebuild.

## Mapping: each directive phase → reality

| # | Directive module | Status | What already fulfils it (or why it's a gap) |
|--:|------------------|--------|---------------------------------------------|
| 106 | MomentSketch | ✅ **SHIPPED** | `core/moment_sketch.py`, `/api/v1/momentsketch` |
| 107 | SemanticMemory | 🟢 **GAP (free)** | composes MinHash+SimHash (both present); no equivalent |
| 108 | AttentionSketch | 🟢 **GAP (free)** | composes Count-Sketch (present); no equivalent |
| 109 | ExperienceDistribution | 🟡 **GAP / partial** | streaming percentile tracker is free; overlaps FORESIGHT calibration + `system_web` metrics |
| 110 | NoveltyDetector | 🟢 **GAP (free)** | composes Bloom+HLL+Count-Min; REVERIE has *surprise* but not this streaming primitive |
| 111 | CausalSketch | 🔵 **EQUIVALENT** | `pradyos/causality` — counterfactual `P(e\|c)−P(e\|¬c)`, stronger than the directive's co-occurrence `P(e\|c)`. `/api/v1/causality` |
| 112 | AnalogyEngine | 🟢 **GAP (free)** | structural MinHash analogy; no equivalent |
| 113 | GoalPlanner | 🔵 **EQUIVALENT** | `pradyos/drive` (Sovereign-gated goals) + `/api/v1/plan` (skill-match → foresight → causal re-weight) |
| 114 | SelfMonitor | 🔵 **MOSTLY EXISTS** | `system_web` (real CPU/RAM/proc) + `warden_grid` (health/incidents); per-module latency p50/p99 is a thin add-on |
| 115 | CompressionController | 🟢 **GAP (free)** | adaptive sketch-parameter tuning; no equivalent |
| 116 | ConsolidationEngine | 🔵 **EQUIVALENT** | `reverie.consolidate()` distils insights into a standing directive |
| 117 | Introspection `/api/v1/mind/*` | 🔵 **MOSTLY EXISTS** | `/api/v1/{reverie,foresight,drive,causality,critic,skills}` already expose cognitive state; a unifying `/mind` facade is optional |
| 118 | CognitiveKernel (bg loop) | 🔵 **MOSTLY EXISTS** | ReverieDriver + AscentDriver are the persistent background loops; an HTTP-request *perception* middleware feeding them is a genuine small gap |
| 119 | Mind Dashboard | 🔵 **EQUIVALENT** | the Sovereign Command Console (`web/console.py`) is a live cognitive dashboard |

Legend: ✅ shipped · 🔵 working equivalent on `main` (building = duplication) ·
🟡 partial overlap · 🟢 genuine, non-duplicative gap.

## The genuine, non-duplicative gaps

These six are real *additive* primitives — sub-linear cognitive sketches that
compose existing structures and do **not** duplicate any merged plane. They are
the only part of the directive worth building, and only under **correct
next-free phase numbers** (not 106–119), after a fresh drift-check to avoid
colliding with concurrent worktrees:

1. **SemanticMemory** — MinHash+SimHash recall (`store/recall/forget`).
2. **AttentionSketch** — Count-Sketch frequency attention with decay.
3. **ExperienceDistribution** — streaming per-metric percentiles + IQR anomaly.
4. **NoveltyDetector** — Bloom+HLL+Count-Min novelty/surprise/cardinality.
5. **AnalogyEngine** — structural `a:b::c:?` via MinHash difference.
6. **CompressionController** — adaptive accuracy/memory parameter tuning.

Plus two thin, optional integrations (not new planes): a unifying `/api/v1/mind/*`
read facade over the existing endpoints, and an HTTP-request *perception*
middleware that feeds the existing background loop.

## Recommendation

Do **not** run the directive verbatim — it would rebuild a shipped module (106)
and create ~7 duplicates of merged work (111/113/114/116/117/118/119), violating
the directive's own Section 5/7. If the cognitive *sketches* are wanted, build
only the six gaps above as ordinary data-structure phases (protocol-clean:
drift-check, 5A+3M, sanity, `prove.py` green) — coordinated against the live tip
and the other worktrees, never against the stale `5473568` snapshot.
