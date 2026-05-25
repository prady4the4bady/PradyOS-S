# AURORA THRONE — API Contract

## Role

The Sovereign Governance Chamber. The **only** Sovereign-visible
surface. The raw CLI is fully hidden (blueprint §VII).

## Constructed surfaces

Per blueprint §13.2, the Throne renders:

| Panel | Source |
|-------|--------|
| Empire Health View | WARDEN GRID `GET /health` |
| Task Queue Status | IMPERIUM `queue.iter_priority_order()` |
| Sovereign Approvals | IMPERIUM `pending_approvals()` |
| WARDEN Incidents | WARDEN GRID `GET /incidents` |
| Audit Tail (last 10) | `AuditLog.tail(10)` |

## Modes

- **Embedded** (default in `pradyos.service`) — receives a live
  `Imperium` instance, can issue approvals.
- **Standalone** — read-only against the checkpoint store + WARDEN HTTP
  API.

## Public methods

```python
throne = Throne(imperium=<Imperium>, audit=<AuditLog>)
throne.run(once=False)              # main loop
throne.run(once=True)               # render once and exit
throne.approve(task_id, by="...")   # only valid in embedded mode
throne.reject(task_id, by="...", reason="...")
throne.stop()
```

## What the Throne does NOT expose

By design, the Throne has **no** method named `exec`, `shell`,
`system`, `run_shell`, or `command`. A unit test
(`tests/test_aurora_throne.py::test_throne_hidden_cli_doctrine`)
enforces this. Adding such a method would be a constitutional
violation: the user must never reach the raw shell through the Throne.

If a Sovereign forensic drill-down is ever needed (blueprint §VII), it
must take place through a separate, explicitly-opted-in inspector
module, never the Throne.

## Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRADY OS — SOVEREIGN EDITION                                        │
│  The machine owns execution. The Sovereign owns strategic authority. │
├─────────────────────────────────┬────────────────────────────────────┤
│  EMPIRE HEALTH                  │  IMPERIUM — TASK QUEUE             │
│  CPU ████░░ 41.0%               │  Total: 8                          │
│  RAM ███░░░ 38.2%               │  Queued: 2 Running: 1              │
│  DISK ████░ 60.0%               │  Recent tasks…                     │
├─────────────────────────────────┼────────────────────────────────────┤
│  SOVEREIGN APPROVALS            │  WARDEN GRID — INCIDENTS            │
│  • Phase 1 build (project_proposal) │  All clear.                    │
├──────────────────────────────────┴────────────────────────────────────┤
│  AUDIT TAIL — LAST 10 ACTIONS                                         │
│  2026-05-22 …  titan_ops  command  0  ran ls -la                      │
└──────────────────────────────────────────────────────────────────────┘
```
