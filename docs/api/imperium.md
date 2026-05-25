# IMPERIUM — API Contract

## Role

Orchestration kernel. The regime coordinator (blueprint §5.1) — kept
deliberately thin so it cannot become a fragile chokepoint. Composed
of four cooperating cores:

- **SchedulerCore** (`TaskQueue`) — priority + FIFO + DAG-aware pop
- **PolicyCore** — constitutional classifier adapter
- **StateCore** (`CheckpointStore`) — checkpoint and resume
- **RecoveryCore** — embedded in `_handle_failure` (Phase 0 stub; Phase 3 expands)

## Task lifecycle

```
                  submit
                    │
                    ▼
   ┌──────────┐  policy classify
   │ QUEUED   │──────────┐
   └────┬─────┘          ▼
        │           ┌───────────┐
        ▼           │ ESCALATED │ ──── Sovereign approve ──┐
   ┌──────────┐     └─────┬─────┘                          │
   │ RUNNING  │           │ Sovereign reject               │
   └────┬─────┘           ▼                                │
        │           ┌───────────┐                          │
        │           │ CANCELLED │◀─────────────────────────┘
        │           └───────────┘
        ▼
   ┌────────────┐   handler.ok          ┌──────────┐
   │ SUCCEEDED  │◀──────────────────────│ RUNNING  │
   └────────────┘                       └──────┬───┘
                                                │ handler.error
                                                ▼
                                          ┌──────────┐
                                          │  FAILED  │ (after max_retries)
                                          └──────────┘
```

## Priority classes

| Class | Rank | Use |
|-------|------|-----|
| `SOVEREIGN` | 0 | Direct Sovereign directive. Preempts everything. |
| `OPERATIONAL` | 1 | Ordinary machine-owned work. |
| `BACKGROUND` | 2 | Idle / nightly self-improvement. |

`TaskQueue.pop_runnable` always picks the lowest rank with all
dependencies satisfied.

## Submitting a task

```python
from pradyos.imperium.kernel import Imperium
from pradyos.imperium.task import ImperiumTask
from pradyos.core.types import Priority

kern = Imperium()
kern.start()
rec = kern.submit(ImperiumTask(
    kind="titan.shell",
    payload={"command": "uname -a", "lane": "unprivileged"},
    intent="check kernel version",
    priority=Priority.OPERATIONAL,
    depends_on=[],
    max_retries=2,
    submitted_by="oracle",
))
```

## Built-in handlers

| Kind | Handler | Notes |
|------|---------|-------|
| `titan.shell` | TitanClient dispatch | requires running TITAN daemon |
| `titan.package` | TitanClient dispatch | |
| `titan.file` | TitanClient dispatch | |
| `titan.service` | TitanClient dispatch | |
| `titan.process` | TitanClient dispatch | |
| `research` | no-op stub | ORACLE wires the real one in Phase 2 |
| `project_proposal` | always escalates | Sovereign approval boundary |

## Custom handlers

```python
def my_handler(task):
    # ... do work ...
    return {"ok": True, "data": ...}

kern.register_handler("custom.kind", my_handler)
```

Handler return contract:

| Key | Meaning |
|-----|---------|
| `ok: True` | Task SUCCEEDED |
| `ok: False, error: str` | Task FAILED (will retry if attempts left) |
| `escalate: True, reason, rule?` | Task ESCALATED (Sovereign approval) |

## Approvals

```python
kern.pending_approvals()           # → [TaskRecord, ...]
kern.approve(task_id, by="...")     # → bool
kern.reject(task_id, by="...", reason="...")  # → bool
```

## Event bus topics

| Topic | Payload |
|-------|---------|
| `imperium.task_queued` | `TaskRecord.to_dict()` |
| `imperium.task_running` | `TaskRecord.to_dict()` |
| `imperium.task_succeeded` | `TaskRecord.to_dict()` |
| `imperium.task_failed` | `TaskRecord.to_dict()` |
| `imperium.task_escalated` | `TaskRecord.to_dict()` |
| `imperium.task_approved` | `TaskRecord.to_dict()` |
| `imperium.task_rejected` | `TaskRecord.to_dict()` |

## Checkpoint / resume

State is appended to `<state_dir>/imperium_tasks.jsonl` on every
transition. On `Imperium.start()` the kernel reads the latest line per
task_id and re-queues any non-terminal task. Phase 3 replaces the JSONL
with a transactional store; the API is stable.

## Dependency graph

`DependencyGraph` provides:

- `add_task(task_id, depends_on)` — rejects cycles via `CycleDetected`
- `topological_order()`
- `parents(task_id)`, `children(task_id)`

The graph is queried by the queue's `pop_runnable` to skip tasks whose
parents have not yet succeeded.
