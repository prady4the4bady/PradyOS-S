# PRADY OS — SOVEREIGN EDITION

> *The machine owns execution. The Sovereign owns strategic authorization.*

PRADY OS is a Linux-based autonomous AI operating system in which a constellation of
specialist agents collectively governs the machine with administrator-level authority.
The human is elevated out of routine operation and positioned as the **Sovereign** who
approves or rejects projects, strategic initiatives, constitutional changes, and
irreversible high-impact actions.

The CLI is fully hidden. Agents own the terminal plane. The Sovereign sees only the
**Governance Chamber** — proposals, outcomes, incidents, approvals.

This is **Phase 0** of the build. It establishes the substrate: the hidden command
runner (TITAN OPS), the health telemetry mesh (WARDEN GRID), the orchestration kernel
(IMPERIUM), and the governance terminal seed (AURORA THRONE).

---

## The Three Laws

1. **Autonomous Execution** — all reversible and policy-compliant operational work is
   executed by the machine without routine human intervention.
2. **Sovereign Approval of Strategic Direction** — projects, strategic initiatives,
   constitutional changes, and irreversible actions cross the Sovereign boundary.
3. **Transparent Power** — broad operational authority is granted only because every
   significant action is observable, attributable, explainable, logged, and
   rollback-aware.

## Approval Boundary

Only the following require human approval:

- New projects surfaced by ORACLE
- Major strategic or architectural shifts
- Irreversible destructive actions on high-value state
- Data exfiltration beyond trusted boundaries
- Constitutional rule changes

Everything else executes autonomously within policy envelopes.

---

## Core Components

| Component | Role | Plane |
|-----------|------|-------|
| `pradyos.titan_ops` | Hidden command runner — admin-grade execution fabric | Execution |
| `pradyos.warden_grid` | Real-time health telemetry and incident detection | Recovery / Substrate |
| `pradyos.imperium` | Task queue, state machine, policy classifier, DAG | Orchestration |
| `pradyos.aurora_throne` | Sovereign Governance Chamber (terminal UI) | Experience |
| `pradyos.core` | Shared substrate — audit log, constitution, bus, IDs | Foundational |
| `pradyos.oracle` | AI reasoning, planning, autonomous proposal loop | Intelligence |
| `pradyos.campaign` | Campaign engine — multi-step DAG execution | Orchestration |
| `pradyos.proving_ground` | Constitutional admission gate | Safety |
| `pradyos.memory_citadel` | Persistent vector memory | Memory |
| `pradyos.sovereign` | Sovereign Web UI + CLI + REPL | Experience |

The raw CLI is never the user surface. `pradyos-throne` is the only sanctioned
entrypoint.

---

## Build Instructions

### Local development (no privilege escalation)

```bash
git clone <repo> pradyos
cd pradyos
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

Launch the governance terminal:

```bash
python -m pradyos.service          # starts all daemons in-process
# in another terminal — but only this one, and only this surface, is sanctioned:
python -m pradyos.aurora_throne    # the Throne
```

### Docker dev environment

```bash
docker compose up --build
```

This brings up TITAN OPS, WARDEN GRID, and IMPERIUM as separate containers and
exposes the WARDEN GRID JSON API on `localhost:9701`.

### Systemd deployment (Sovereign build)

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pradyos-titan.service \
                            pradyos-warden.service \
                            pradyos-imperium.service
# Throne is launched on Sovereign login, not as a service.
```

---

## Repo Layout

```
pradyos/
├── core/            # shared substrate
├── titan_ops/       # hidden command runner (Plane 2)
├── warden_grid/     # health telemetry + incident mesh (Plane 1/9)
├── imperium/        # orchestration kernel (Plane 3)
└── aurora_throne/   # governance terminal (Plane 10)
docs/                # architecture + API contracts
deploy/              # systemd units + Dockerfile
tests/               # pytest suite
var/                 # audit log + checkpoint state (gitignored)
```

---

## Status

**Phase 7 — Complete.** All 35 test modules green (82.7 s). Audit hooks,
metrics hooks, retry hooks, config watcher, REPL extensions, and deploy
pipeline are provably wired.

**Phase 8 — Complete.** All 37 test modules green. ORACLE autonomous proposal
loop and Campaign ↔ Proving Ground admission bridge provably wired.

**Phase 9 — Complete.** All 37 test modules green. Four deliverables:
- ✅ 9A: Production systemd units for **all five services** — `pradyos-titan`,
  `pradyos-warden`, `pradyos-imperium`, `pradyos-oracle` (new), and
  `pradyos-admission` (new). All units restart on failure, log to journald,
  and carry a full set of systemd sandboxing directives (`NoNewPrivileges`,
  `ProtectSystem=strict`, `PrivateTmp`, `PrivateDevices`,
  `ProtectKernelModules`, `ProtectControlGroups`, `RestrictNamespaces`,
  `LockPersonality`, `MemoryDenyWriteExecute`, `SystemCallFilter`). Dependency
  ordering: WARDEN + TITAN → IMPERIUM → ORACLE → ADMISSION.
- ✅ 9B: Docker hardening — `deploy/Dockerfile` upgraded to Python 3.12,
  `COPY --chown=pradyos` throughout. `deploy/docker-compose.yml` gains
  `oracle` and `admission` services wired with healthchecks
  (`/oracle/status` and
import-probe respectively), plus fleet-wide
  `cap_drop: [ALL]`, `security_opt: no-new-privileges:true`,
  `read_only: true`, `tmpfs: /tmp`, and a single named volume
  `pradyos-var` for audit log + state persistence. Secrets managed via
  `deploy/secrets.env` (template at `deploy/secrets.env.example`).
- ✅ 9C: `tests/test_deploy.py` extended with 28 new assertions covering
  new systemd units, Docker hardening directives, oracle/admission
  service definitions, and healthcheck presence. All 37 modules remain green.
- ✅ 9D: README updated.

**Phase 10 — Complete.** All 38 test modules green (28.7 s). Redis
inter-process bus live across Docker and systemd planes:
- ✅ 10A: `pradyos/core/redis_bus.py` — `RedisBus` drop-in replacement for
  `EventBus` using redis-py Pub/Sub. A daemon thread polls
  `pubsub.get_message()` and dispatches to registered callbacks. Regular
  topics use `SUBSCRIBE`; the wildcard `"*"` topic uses `PSUBSCRIBE("*")`.
  Subscriber faults are isolated; unsubscribe triggers `UNSUBSCRIBE` /
  `PUNSUBSCRIBE` when the last handler is removed.
- ✅ 10B: `pradyos/core/bus.py` — `get_bus()` factory updated. When
  `PRADYOS_BUS_BACKEND=redis`, returns `RedisBus`; otherwise the existing
  in-process `EventBus`. Zero call-site changes.
- ✅ 10C: `deploy/docker-compose.yml` — `redis:7-alpine` service added with
  a `redis-cli ping` healthcheck and a named volume (`pradyos-redis`). All
  application services gain `PRADYOS_BUS_BACKEND=redis`,
  `PRADYOS_REDIS_URL=redis://redis:6379/0`, and `depends_on: [redis]`.
- ✅ 10D: All six `deploy/systemd/*.service` files (`pradyos-titan`,
  `pradyos-warden`, `pradyos-imperium`, `pradyos-oracle`, `pradyos-admission`,
  `pradyos-throne`) updated with
  `Environment=PRADYOS_BUS_BACKEND=redis` and
  `Environment=PRADYOS_REDIS_URL=redis://127.0.0.1:6379/0`.
- ✅ 10E: `tests/test_redis_bus.py` — 16 tests using `fakeredis` (no real
  Redis server required). Covers pub/sub, wildcard, unsubscribe, fault
  isolation, payload round-trip, and `get_bus()` factory.
- ✅ 10F: `pyproject.toml` dev deps extended with `redis>=5.0` and
  `fakeredis>=2.0`. `deploy/secrets.env.example` documents new env vars.


**Phase 11 — Complete.** All 41 test modules green. Autonomous self-healing live:
- ✅ 11A: `pradyos/imperium/self_heal.py` — `SelfHealEngine` with `heal()`,
  `is_quarantined()`, `release_quarantine()`, `quarantine_list()`. Loads
  latest `SnapshotStore` entry as rollback reference, quarantines offending
  tasks in-memory + persisted to `var/state/quarantine.json`, publishes
  `system.self_heal` bus event (WARDEN auto-raises incident via `system.*`
  wildcard), and writes a structured audit entry.
- ✅ 11B: `pradyos/imperium/kernel.py` — `Imperium.rollback()` method added;
  `Imperium._self_heal_hook()` callback wired into `RecoveryCore.on_exhausted`
  so any task that exhausts its retry budget is healed autonomously.
  `pradyos/imperium/recovery.py` extended with `on_exhausted` callback slot.
- ✅ 11C: `pradyos/imperium/exceptions.py` — `TaskNotFound` custom exception.
- ✅ 11D: `tests/test_self_heal.py` — 22 tests: `HealResult` correctness,
  quarantine persistence, `is_quarantined`, `release_quarantine`, bus events,
  audit entries, kernel integration (auto-heal on dead-letter), idempotency,
  snapshot reference, multi-task quarantine, and WARDEN notification.
- ✅ 11E: `scripts/prove.py` updated; README Phase Map updated.

**Phase 13 — Complete.** All 43 test modules green. Live campaign monitor —
the Sovereign watches every campaign step execute in real time:
- ✅ 13A: `pradyos/aurora_throne/campaign_monitor.py` — `CampaignMonitor` class
  with `deque(maxlen=100)` step_timeline and `deque(maxlen=50)` titan_ops_feed ring
  buffers, `get_snapshot()` → `CampaignMonitorSnapshot` (active_campaigns,
  step_timeline, titan_ops_feed), `start()` / `stop()` subscribe/unsubscribe on
  the bus wildcard, `_on_campaign_event()` and `_on_titan_event()` route events by
  prefix.
- ✅ 13B: `pradyos/sovereign_web.py` — `GET /api/v1/campaigns/monitor` endpoint
  wired into `create_app()` via new `campaign_monitor` parameter. Returns
  `CampaignMonitorSnapshot.to_dict()` as JSON (200); falls back to zeroed snapshot
  when no monitor is injected.
- ✅ 13C: `pradyos/aurora_throne/textual_app.py` — `CampaignMonitorScreen`
  (Textual `Screen` subclass) renders three live panels: **Active Campaigns** |
  **Step Timeline** | **TITAN Ops Feed**. Refreshes every 2 s. Accessible via
  the `c` keybind from `ThroneApp`; `escape` / `q` dismisses.
- ✅ 13D: `tests/test_campaign_monitor.py` — 20 unit tests: snapshot type,
  ring-buffer caps (100/50) and eviction, active_campaigns reflection,
  _on_campaign_event / _on_titan_event appends with ts, start/stop
  subscribe/unsubscribe, JSON-serialisability, dict key presence, ring-buffer
  independence, and idempotent double-stop.
- ✅ 13E: `tests/test_campaign_monitor_web.py` — 10 FastAPI TestClient tests:
  HTTP 200, required keys, list types, active_campaigns reflection, Content-Type
  application/json, ts in timeline entries, topic in titan feed entries, and safe
  fallback with no monitor injected.
- ✅ 13F: `scripts/prove.py` updated with both new test modules (43 total).
- ✅ 13G: README Phase Map updated; Phase 14 planned.

**Phase 12 — Complete.** All 44 test modules green. Live observability
dashboard — the Sovereign sees everything in real time:
- ✅ 12A: `pradyos/aurora_throne/dashboard.py` — `ObservabilityDashboard`
  class with a `deque(maxlen=50)` ring buffer, `get_live_snapshot()` →
  `DashboardSnapshot` (bus_events, quarantine, system_health), `start()`
  / `stop()` subscribe/unsubscribe on the bus wildcard, and a
  `_on_bus_event()` subscriber that populates the ring buffer and updates
  `last_event_ts`. Health thresholds: **ok** (dlq=0, active<5),
  **degraded** (dlq≥1 or active≥5), **critical** (dlq≥5 or active≥20).
- ✅ 12B: `pradyos/sovereign_web.py` — `GET /api/v1/dashboard` endpoint
  wired into the existing FastAPI app via a new `observability_dashboard`
  constructor parameter. Returns `DashboardSnapshot.to_dict()` as JSON
  (200); falls back to a zeroed snapshot when no dashboard is injected.
- ✅ 12C: `pradyos/aurora_throne/textual_app.py` — `DashboardScreen`
  (Textual `Screen` subclass) renders three live panels: **Live Bus
  Events** | **Quarantine** | **System Health**. Refreshes every 2 s.
  Accessible via the `d` keybind from `ThroneApp`; `escape` / `q`
  dismisses and returns to the main Throne.
- ✅ 12D: `tests/test_dashboard.py` — 20 unit tests: snapshot type,
  ring-buffer cap (50) and eviction, quarantine reflection, health
  thresholds (ok/degraded/critical), start/stop subscribe/unsubscribe,
  _on_bus_event appends, last_event_ts tracking, active_tasks and
  dead_letter_count from kernel, JSON-serialisability, dict field
  presence, and idempotent double-stop.
- ✅ 12E: `tests/test_dashboard_web.py` — 10 FastAPI TestClient tests:
  HTTP 200, required keys (bus_events / quarantine / system_health),
  quarantine state reflection, status field validity, bus_events as
  list, health metric keys, and Content-Type: application/json.
- ✅ 12F: `scripts/prove.py` updated with both new test modules (44 total).
- ✅ 12G: README Phase Map updated; Phase 13 planned.

### Phase Map

| Phase | Name | Status |
|-------|------|--------|
| 0 | Substrate (TITAN, WARDEN, IMPERIUM, THRONE) | Complete |
| 1 | Oracle AI Core + Planner | Complete |
| 2 | Memory Citadel | Complete |
| 3 | Campaign Engine | Complete |
| 4 | Warden Phase 4 | Complete |
| 5 | Sovereign Web + CLI + REPL | Complete |
| 6 | Snapshot, Healthcheck, Watchdog | Complete |
| 7 | Audit Hooks, Metrics Hooks, Retry Hooks, Config Watcher | Complete |
| 8 | Autonomous Proposal Loop + Admission Bridge | Complete |
| 9 | Deployment (systemd hardening + Docker hardening) | Complete |
| 10 | Redis Inter-Process Event Bus | Complete |
| 11 | Self-Healing (auto-rollback, quarantine enforcement) | Complete |
| 12 | Observability Dashboard (live bus events, quarantine, system health) | Complete |
| 13 | Live Campaign Monitor — real-time campaign progress, step execution timeline, and TITAN ops feed in Aurora Throne | Complete |
| 14 | Policy Engine — Sovereign-configurable task approval rules, rate limits, and constitutional guardrails enforced by IMPERIUM at dispatch time | Planned |
