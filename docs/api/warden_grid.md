# WARDEN GRID — API Contract

## Role

Continuous host telemetry monitor with incident detection. Serves a
local JSON HTTP API the rest of the constellation reads from. Phase 0
seed of the autonomous recovery mesh (blueprint §5.5).

## HTTP endpoints

Default bind: `127.0.0.1:9701` (overridable via `PRADYOS_WARDEN_HOST`
and `PRADYOS_WARDEN_PORT`).

### `GET /` or `GET /health`

Returns the latest health snapshot:

```json
{
  "timestamp": 1716340000.0,
  "hostname": "sovereign-prime",
  "platform": "Linux-…",
  "uptime_sec": 12345.0,
  "cpu_percent": 42.7,
  "cpu_count": 16,
  "load_average": [1.2, 0.9, 0.7],
  "ram_percent": 55.0,
  "ram_total_mb": 32768.0,
  "ram_used_mb": 18000.0,
  "swap_percent": 0.0,
  "disk": [
    {"mount": "/", "device": "/dev/nvme0n1p2", "fstype": "btrfs",
     "total_mb": 1000000.0, "used_mb": 600000.0, "percent": 60.0}
  ],
  "inode": [{"mount": "/", "percent": 12.0, "total": 4194304, "free": 3687472}],
  "network_io": {"bytes_sent": 1234, "bytes_recv": 5678,
                  "packets_sent": 1, "packets_recv": 1,
                  "errin": 0, "errout": 0},
  "process_count": 412,
  "gpus": [
    {"index": 0, "name": "RTX 4090", "util_percent": 8.0,
     "mem_used_mb": 1024.0, "mem_total_mb": 24576.0, "temperature_c": 42.0}
  ],
  "services": [
    {"name": "pradyos-titan", "pid": 1234, "running": true,
     "cpu_percent": 0.1, "memory_rss_mb": 38.4}
  ],
  "has_nvml": true
}
```

### `GET /incidents`

Open incidents only:

```json
{
  "open": [
    {
      "incident_id": "inc_…",
      "signature": "abc123…",
      "severity": "CRIT",
      "component": "disk",
      "summary": "disk / 97.0%",
      "detail": {"mount": "/", "device": "/dev/…", "value": 97.0, "warn": 85, "crit": 95},
      "first_seen": 1716340000.0,
      "last_seen": 1716340500.0,
      "occurrences": 17,
      "resolved_at": null,
      "rollback_hook": null,
      "is_open": true
    }
  ]
}
```

### `GET /incidents/all`

All incidents (open + resolved).

### `GET /services`

Just the `services` array from the snapshot.

### `GET /thresholds`

Currently active thresholds.

### `GET /ping`

`{"ok": true, "agent": "warden_grid"}` — liveness check.

## Incident model

Coalescing key: `sha1(component | kind | target)[:12]`. The same
recurring symptom collapses into one open incident with monotonically
escalating severity (`INFO` → `WARN` → `CRIT` → `FATAL`). Resolution is
either explicit (`store.resolve(sig_or_id)`) or implicit (service
restored, threshold returned to safe range).

## Thresholds

Defaults (overridable per-field via `PRADYOS_THRESHOLD_<NAME>`):

| Field | warn | crit |
|-------|------|------|
| CPU % | 80 | 95 |
| RAM % | 80 | 95 |
| Disk % | 85 | 95 |
| Inode % | 85 | 95 |
| GPU util % | 85 | 97 |
| Load 1m | 4.0 | 8.0 |

Poll interval default `5.0s`, override via `PRADYOS_THRESHOLD_INTERVAL_SEC`.

## Audit attribution

Every new incident writes an audit record:

- `agent_id = "warden_grid"`
- `kind = "incident"`
- `detail.incident_id`, `detail.signature`, `detail.severity`,
  `detail.component`, `detail.value`, etc.

## Event bus topics

| Topic | When |
|-------|------|
| `warden.incident` | Each time a new incident is opened |

Payload: `{incident_id, severity, component, summary, rollback_hook}`.

## Watched services

Comma-separated names via `PRADYOS_WATCHED_SERVICES` env var or
`WardenMonitor(watched_services=[…])`. WARDEN searches running
processes by name or cmdline match. A missing service raises a CRIT
incident with `rollback_hook = "systemctl start <name>"`.
