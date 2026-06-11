# TITAN OPS — API Contract

## Role

Hidden command runner. The execution plane of PRADY OS. Translates
structured `TitanInstruction` objects into isolated subprocess
invocations with full audit attribution.

## Wire protocol (daemon)

Newline-delimited JSON over a Unix domain socket (default
`/run/pradyos/titan.sock`) or TCP fallback (`127.0.0.1:9700`).

### Request

```json
{
  "instruction_id": "ti_…",          // optional — generated if absent
  "agent_id": "imperium",             // REQUIRED — caller attribution
  "kind": "shell"                     // REQUIRED — one of:
                                      //   shell | package | file | service | process
  "lane": "unprivileged",             // default: unprivileged
                                      //   options: unprivileged | privileged | sandbox
  "command": "ls -la /etc",           // for kind=shell
  "args": {                           // kind-specific
    "manager": "apt",                 // for kind=package
    "op": "install",
    "package": "htop"
  },
  "cwd": "/tmp",
  "env": { "FOO": "bar" },
  "timeout_sec": 60,
  "rollback_hook": "apt purge htop",  // opaque ref; stored in registry
  "correlation_id": "tk_…",           // ties this command to an IMPERIUM task
  "intent": "install htop"            // human-readable narration
}
```

### Response

```json
{
  "ok": true,
  "result": {
    "instruction_id": "ti_…",
    "agent_id": "imperium",
    "lane": "unprivileged",
    "argv": ["ls", "-la", "/etc"],
    "exit_code": 0,
    "stdout": "…",
    "stderr": "",
    "started_at": 1716340000.0,
    "finished_at": 1716340000.5,
    "timed_out": false,
    "escalated": false,
    "escalation_reason": null,
    "rollback_hook": null,
    "correlation_id": null,
    "succeeded": true,
    "duration_sec": 0.5
  }
}
```

If the executor or the constitution rejects the instruction:

```json
{ "ok": false, "error": "…why…" }
```

Constitutional escalation returns `ok: true` but
`result.escalated == true` and `result.exit_code == null`.

## Instruction kinds

| Kind | Required args | Notes |
|------|----------------|-------|
| `shell` | `command` (string) | argv split via `shlex` |
| `package` | `args.package`, `args.manager` | managers: apt, pip, dnf, yum, pacman |
| `file` | `args.path`, `args.op` | ops: stat, read, list, remove, remove_tree, mkdir, chmod, chown, write |
| `service` | `args.unit`, `args.op` | systemctl wrapper |
| `process` | `args.op` | ops: list, kill (with `pid`), tree |

## Execution lanes

| Lane | Effect |
|------|--------|
| `unprivileged` | No prefix; runs as the daemon user. Default. |
| `privileged` | Prepends `sudo -n` (non-interactive), or runs as root if already root. Sets `PRADYOS_PRIVILEGE_DEGRADED=1` if neither path exists. |
| `sandbox` | Phase 0: env-only marker (`PRADYOS_SANDBOX=1`). Phase 4: kernel-level isolation. |

## Audit attribution

Every execution writes an audit record with:

- `agent_id` — the caller (NOT `titan_ops` itself)
- `kind` — `"command"`
- `summary` — `intent` or rendered argv
- `detail.instruction_id`, `detail.lane`, `detail.argv`,
  `detail.stdout_tail` (last 2KB), `detail.stderr_tail` (last 2KB),
  `detail.timed_out`, `detail.constitutional_rule`, `detail.executed_by`
- `exit_code`
- `rollback_hook` (if supplied)
- `correlation_id` (if supplied)

The audit record is the only legal evidence of an execution.

## Event bus topics

| Topic | When |
|-------|------|
| `titan.completed` | After every execution (success or failure) |
| `titan.escalated` | When the constitution rejects an instruction |

Payload schema for both: `{instruction_id, correlation_id, succeeded, exit_code, audit_record_id, …}`.

## Rollback registry

Any instruction that supplies `rollback_hook` is registered in
`TitanExecutor.rollback`. A later instruction, a Recovery Core decision,
or a Sovereign directive may consult the registry and execute the hook
to undo the action.

## Python client (`TitanClient`)

```python
from pradyos.titan_ops.daemon import TitanClient
client = TitanClient()
resp = client.send({
    "agent_id": "imperium",
    "kind": "shell",
    "command": "uname -a",
    "intent": "check kernel",
})
```
