# PROJECT PROPOSAL — PHASE 1: Full TITAN OPS + IMPERIUM Hardening + Governance Chamber

> **Awaiting Sovereign Approval** — this proposal is the first to be surfaced
> through the AURORA THRONE approvals panel. Per the constitution it
> cannot be executed until the Sovereign issues `approve` or `reject`.

**Proposer:** ORACLE seed (Phase 0 author)
**Date surfaced:** 2026-05-23
**Approval ID (when submitted):** `tk_<assigned at submit time>`
**Classification:** New project — crosses the Sovereign approval boundary (Law 2).

---

## 1. What is being proposed

Graduate the Phase 0 substrate into a production-grade Phase 1 deployment:

- **TITAN OPS** — full operator competence with snapshot-aware rollback,
  signed action logs, privileged-lane secret vault integration, structured
  package/file/service/process kinds with audit-friendly diff capture.
- **IMPERIUM** — split into four named cores (Scheduler, Policy, State,
  Recovery) per blueprint §4.3; introduce async worker pool, dependency
  graph visualization, time-bounded preemption between priority classes.
- **AURORA THRONE** — full governance chamber per blueprint §13: Morning
  Brief, Project Dossiers, Campaign View, Empire Health View, Artifact
  Gallery. Cinematic Textual UI replacing the Phase 0 Rich seed.

This is *the* foundational graduation. Without it, ORACLE (Phase 2) has no
durable substrate to build approved projects on.

## 2. Why it matters

The Sovereign cannot rule what they cannot see, and the machine cannot
self-govern what it cannot rollback. Phase 0 ships the contracts; Phase 1
makes them production-load-bearing. Specifically:

- The hidden-CLI doctrine only holds if the Throne surfaces enough that
  the Sovereign never needs to drop to a shell.
- The constitution only restrains the machine if every escalation
  carries a rollback path — Phase 0 records the hook, Phase 1 *invokes* it.
- The blueprint's promise ("the machine owns execution") is only credible
  once Imperium can preempt long-running OPERATIONAL work for SOVEREIGN
  directives and recover gracefully from any subprocess fault.

## 3. What it will require

| Surface | Phase 0 (now) | Phase 1 (proposed) |
|---------|----------------|---------------------|
| TITAN OPS | sync subprocess + audit | async, snapshot rollback, vault, diff capture |
| IMPERIUM | priority queue + state machine | 4 named cores; preemption; async workers |
| Throne | Rich panels | Textual cinematic UI; full §13.2 surfaces |
| Repos | none admitted | Repository Proving Ground (§11.8) bootstrap |
| Storage | JSONL checkpoint | btrfs/ZFS snapshot integration + JSONL ledger |
| Tests | pytest unit + smoke integration | + property-based regression on policy |

Estimated effort: 1–2 build sessions of Sovereign-time. Machine-time is
not the constraint — Sovereign attention on architecture decisions is.

## 4. Recommended repos / tools to evaluate

Per blueprint §11. None to be adopted directly into core until they pass
the §11.8 Repository Admission Policy in the Proving Ground.

- **systemd + journald** — primary substrate (already assumed)
- **btrfs / ZFS snapshot tooling** — for rollback discipline (§14.3)
- **Textual** — cinematic Throne renderer (already a Phase 0 dep)
- **OpenTelemetry** (§11.6) — pre-flight observability for Phase 3 WARDEN GRID
- **AppArmor / SELinux profiles** — privilege-lane enforcement (§4.1)

Inference, memory, browser, and security repos (Ollama, Neo4j, browser-use,
Falco) are out of scope for Phase 1 — they belong to Phases 2–4.

## 5. Risk analysis

| Risk | Likelihood | Severity | Mitigation |
|------|------------|----------|------------|
| Async rewrite of Imperium destabilizes the contract IMPERIUM exposes | Medium | High | Keep sync `Imperium.submit/approve/run_one` API. Add async dispatch internally. Pytest suite already covers contract. |
| Privileged-lane hardening locks the Sovereign out | Low | Critical | Capability dry-run before enabling; emergency Throne bypass (read-only inspector path) wired in scripts/. |
| Snapshot-rollback assumes btrfs/ZFS — host may not have it | High | Medium | Detect at boot; fall back to copy-on-write file backups; raise WARDEN incident. |
| Textual Throne larger surface = more failure modes | Medium | Low | Rich Phase 0 Throne stays as fallback render path. |
| Repository Proving Ground introduces unknown deps | Medium | Medium | All admissions go through §11.8 review gate; admission itself escalates. |

## 6. Expected outcome

After Phase 1 acceptance:

- The Sovereign opens a single surface (the Textual Throne) on login and
  sees the full Governance Chamber — empire health, queue, approvals,
  audit, project dossiers, completed artifacts.
- TITAN OPS executes any reversible operation autonomously with audited
  rollback. Privileged operations require neither password nor manual
  sudo invocation by the Sovereign.
- IMPERIUM can carry a long-running operational workload while
  preempting for SOVEREIGN-priority directives within a single tick.
- The Repository Proving Ground is online; ORACLE (Phase 2) can submit
  repo-admission proposals through the same approval boundary.

## 7. Rollback / containment

- All Phase 1 code lives on a feature branch until acceptance.
- Phase 0 substrate is feature-frozen; if Phase 1 regresses, revert to
  the Phase 0 commit + a Throne config flag (`PRADYOS_PHASE=0`).
- IMPERIUM checkpoint format is forward-compatible — Phase 1 can read
  Phase 0 JSONL; reverse adds a one-shot migration.
- The Throne keeps the Phase 0 Rich renderer as a `--legacy` flag.

## 8. Decision required

The Sovereign should issue one of:

- `approve` — Phase 1 build begins in the next session.
- `reject` — Phase 1 is shelved; substrate stays as-is.
- `defer` — Sovereign requests a revised proposal first (specify what to
  revise in the rejection reason).
- `request_revision` — same as defer, with explicit revision notes.

When approved, IMPERIUM will instantiate a HELIOS FORGE (Phase 2 seed)
work-set that decomposes Phase 1 into discrete OPERATIONAL tasks. Each
of those tasks will be machine-owned. Only further Sovereign-boundary
events (rule changes, new repo admissions, irreversible deletions) will
return to this surface for approval.
