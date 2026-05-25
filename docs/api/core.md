# pradyos.core — Substrate API

Shared substrate every plane depends on.

## Audit log

```python
from pradyos.core.audit import get_audit_log

log = get_audit_log()
rec = log.record(
    agent_id="titan_ops",
    kind="command",            # 'command' | 'incident' | 'state' | 'event' | 'approval'
    summary="installed htop",
    detail={"argv": ["apt-get", "install", "-y", "htop"]},
    exit_code=0,
    rollback_hook="apt-get purge -y htop",
    correlation_id="tk_…",     # ties to an IMPERIUM task
)
log.tail(10)                   # last 10 in-memory records
log.read_from_disk(limit=100)  # rehydrate from disk
log.subscribe(callback)        # fn(rec) — fires on every write
```

Append-only JSONL at `$PRADYOS_AUDIT_PATH` (default `<repo>/var/log/audit.jsonl`).

## Event bus

```python
from pradyos.core.bus import get_bus

bus = get_bus()
bus.subscribe("imperium.task_succeeded", lambda topic, payload: ...)
bus.subscribe("*", lambda topic, payload: ...)  # wildcard
bus.publish("topic.name", {"k": "v"})
```

## Constitution

```python
from pradyos.core.constitution import default_constitution, ApprovalDomain

c = default_constitution()
d = c.classify(
    kind="titan_shell",
    summary="install package",
    detail={"command": "apt-get install -y htop"},
)
# d.domain ∈ {ApprovalDomain.AUTONOMOUS, ApprovalDomain.APPROVAL_REQUIRED}
# d.reason, d.matched_rule, d.suggested_narrowing
```

## IDs

```python
from pradyos.core.ids import new_id
new_id("tk")   # → "tk_01hnq8mz4x_a3b7"
```

40-bit time component + 20 random bits, Crockford-ish alphabet, sorts
roughly chronologically.

## Types

```python
from pradyos.core.types import Priority, TaskState, ExecutionLane, AgentID

Priority.SOVEREIGN.rank == 0
TaskState.SUCCEEDED.terminal == True
ExecutionLane.PRIVILEGED.value == "privileged"
```
