# PRADY OS — Phase 0 Architecture

Phase 0 establishes the **substrate** of the Sovereign OS. It is the
load-bearing foundation that every later phase is built on. The five
components in this phase implement the lowest five rungs of the
ten-plane model from the master blueprint.

## Plane mapping

| Component | Blueprint plane | Blueprint section |
|-----------|------------------|-------------------|
| `pradyos.core` | Substrate (cross-cutting) | §2.3, §4.1 |
| `pradyos.titan_ops` | Execution Plane | §4.2, §5.2 |
| `pradyos.warden_grid` | Substrate + Self-Improvement Plane | §4.1, §4.9, §5.5 |
| `pradyos.imperium` | Orchestration Plane | §4.3, §5.1 |
| `pradyos.aurora_throne` | Experience Plane | §4.10, §13 |

## Data flow

```
                ┌──────────────────────────────────────────┐
                │             AURORA THRONE                │
                │       (Sovereign Governance Chamber)      │
                └────▲──────────────────────────────▲──────┘
                     │ render data                   │ approve/reject
                     │                                │
                ┌────┴──────┐               ┌────────┴─────────┐
                │ WARDEN    │               │     IMPERIUM     │
                │ GRID HTTP │               │ (priority queue, │
                │  :9701    │               │  state machine,  │
                │  /health  │               │  policy, DAG)    │
                └────▲──────┘               └────────▲─────────┘
                     │ telemetry                     │ JSON
                     │                                │ TitanInstruction
                ┌────┴──────────────────────────────┴──────────┐
                │              TITAN OPS daemon                │
                │  (unprivileged + privileged subprocess lanes)│
                └──────────────────────────────────────────────┘
                     │
                     ▼
                ┌──────────────────────────────────────────┐
                │             AUDIT LEDGER                 │
                │ append-only JSONL — every action logged  │
                └──────────────────────────────────────────┘
```

All four daemons publish to a shared event bus
(`pradyos.core.bus.EventBus`) and write to a shared audit ledger
(`pradyos.core.audit.AuditLog`). The audit ledger is the linchpin: the
constitution permits the machine's broad authority **only because**
every action is observable, attributable, explainable, logged, and
rollback-aware.

## The constitution (BASTION seed)

Implemented in `pradyos.core.constitution`. Classifies a request as
either AUTONOMOUS (Domain B — machine acts) or APPROVAL_REQUIRED
(Domain A — Sovereign acts). Default rules block:

- New project proposals (`new_project_proposal`)
- Irreversible destructive ops (`rm -rf /`, `DROP TABLE`, `mkfs`, …)
- Data egress (`scp`, `aws s3 cp`, `rclone`)
- Privilege modification (`usermod -aG sudo`, `chmod u+s`, …)
- Constitutional changes themselves

The constitution is applied **twice** for defence in depth: once by
IMPERIUM's PolicyCore at submission time, and again by TITAN OPS's
executor immediately before subprocess launch.

## Hidden CLI doctrine

The blueprint requires the CLI to be fully hidden (§VII). Phase 0
enforces this:

1. The `TitanExecutor` never accepts free-form `subprocess.shell=True`.
2. Every TITAN OPS execution path passes through a structured
   `TitanInstruction`.
3. The Throne (`pradyos.aurora_throne.Throne`) exposes only
   `approve` / `reject` — no `exec`, no `system`, no `run_shell`. A unit
   test (`test_throne_hidden_cli_doctrine`) guards this.
4. The single sanctioned Sovereign entrypoint is
   `python -m pradyos.service` which launches the Throne.

## Future-phase hooks already wired

- `ExecutionLane.SANDBOX` — NIGHT CITADEL (Phase 4)
- `kind='research'` handler — ORACLE (Phase 2)
- `kind='project_proposal'` handler — ORACLE (Phase 2)
- `RollbackRegistry` — Recovery Core (Phase 1+)
- `EventBus` topics `imperium.*`, `titan.*`, `warden.*` —
  cross-agent coordination starting Phase 1
