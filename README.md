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

**Phase 16 — Complete.** All 49 test modules green. OTel-compatible telemetry pipeline — every significant OS event emits a structured span stored in a ring buffer and queryable via API:
- ✅ 16A: `pradyos/core/telemetry.py` — `TelemetrySpan` dataclass (span_id, trace_id, parent_id, name, service, start_ts, end_ts, status, attributes) with `duration_ms()` and `to_dict()`. `TelemetryCollector` ring-buffer (collections.deque maxlen=500) with `start_span()`, `finish_span()`, `record()` (one-shot), `get_spans(limit, service, status)` returning most-recent-first, `clear()`, and `__len__()`. Thread-safe via threading.Lock. Auto-generates UUID4 hex span_id and trace_id. `finish_span()` returns None for unknown span_id — never raises.
- ✅ 16B: `pradyos/sovereign_web.py` — `GET /api/v1/telemetry` endpoint wired via optional `telemetry` param in `create_app()`. Query params: `limit` (int, default 100, max 500), `service` (str|None), `status` (str|None). Returns `{"spans": [...], "count": int}`. Safe empty response `{"spans": [], "count": 0}` when telemetry not injected.
- ✅ 16C: `tests/test_telemetry.py` — 20 unit tests covering start_span status/id generation/explicit trace_id/append, finish_span status/end_ts/merge/unknown-id, record default/duration_ms/error, get_spans list/limit/service filter/status filter/order, clear, maxlen eviction, and duration_ms None vs computed.
- ✅ 16D: `tests/test_telemetry_web.py` — 10 FastAPI TestClient tests: HTTP 200, spans/count keys, spans is list, count==len(spans), limit param, service filter, status filter, count reflects filter, no-telemetry empty response.
- ✅ 16E: `scripts/prove.py` updated with both new test modules (49 total).
- ✅ 16F: README Phase Map updated; Phase 17 planned.

**Phase 17 — Complete.** All 51 test modules green. Sovereign Memory Graph — a knowledge graph layer where the OS stores facts, relationships, and inferences about campaigns, tasks, and system state — queryable via API and visualised in the Aurora Throne TUI:
- ✅ 17A: `pradyos/core/memorygraph.py` — `GraphNode` and `GraphEdge` dataclasses with `to_dict()`. `SovereignMemoryGraph` with bounded storage (maxnodes/maxedges), LRU-by-age eviction, `add_node()`, `add_edge()`, `get_node()`, `get_edge()`, `neighbours(relation=None)`, `query_nodes(kind, label)` sorted newest-first, `remove_node()` cascading edge removal, `remove_edge()`, `stats()`, `clear()`. Thread-safe via `threading.Lock`. Auto-generates UUID4 hex ids.
- ✅ 17B: `pradyos/sovereign_web.py` — `GET /api/v1/graph/stats` returns `{"nodes": int, "edges": int}`; `POST /api/v1/graph/nodes` body `{kind, label, node_id?, attributes?}` returns new node dict; `GET /api/v1/graph/nodes?kind&label&limit` returns `{"nodes": [...], "count": int}`; `GET /api/v1/graph/nodes/{node_id}/neighbours?relation` returns `{"neighbours": [...], "count": int}`. Wired via new `graph` param in `create_app()`. Safe empty responses when graph not injected.
- ✅ 17C: `tests/test_memorygraph.py` — 20 unit tests covering add_node kind/label/auto-id/explicit-id/stats, add_edge fields/auto-id/stats, get_node hit/miss, get_edge hit, neighbours basic/relation-filter, query_nodes kind/label filter, remove_node true/false/cascade, remove_edge true/false, maxnodes eviction, and clear.
- ✅ 17D: `tests/test_memorygraph_web.py` — 10 FastAPI TestClient tests: GET stats 200, stats keys, POST node 200, POST required keys, GET nodes 200/shape, count==len after POST, kind filter, GET neighbours 200, neighbours shape/count, no-graph safe empty.
- ✅ 17E: `scripts/prove.py` updated with both new test modules (51 total).
- ✅ 17F: README Phase Map updated; Phase 18 planned.

**Phase 18 — Complete.** All 53 test modules green. Sovereign Event Ledger — an append-only, cryptographically chained audit log where every OS event is committed as a hash-chain entry that can be verified in O(n) time:
- ✅ 18A: `pradyos/core/ledger.py` — `LedgerEntry` dataclass with `entry_id` (uuid4 hex), `prev_hash`, `entry_hash` (SHA-256), `service`, `event`, `payload`, `ts`. `EventLedger` class: thread-safe `append()`, `verify()`, `get_entries()` with optional service/event filters, `__len__`, `clear()`.
- ✅ 18B: `pradyos/sovereign_web.py` — patched to add optional `ledger` param to `create_app()`; `GET /api/v1/ledger` returns `{entries, count}` with `limit`, `service`, `event` query params; `GET /api/v1/ledger/verify` returns `{valid, count}`. Safe empty responses when no ledger injected.
- ✅ 18C: `tests/test_ledger.py` — 20 unit tests covering append, verify, get_entries, len, clear, tamper detection.
- ✅ 18D: `tests/test_ledger_web.py` — 10 FastAPI TestClient tests for both ledger endpoints.
- ✅ 18E: `scripts/prove.py` updated with both new test modules (53 total).
- ✅ 18F: README Phase Map updated; Phase 19 planned.

**Phase 19 — Complete.** All 55 test modules green. Sovereign Intent Engine — a rule-based planner that evaluates runtime context (memory graph, active campaigns, telemetry spans, event ledger) against a configurable rule set and emits ranked `IntentSuggestion` objects with action, target, reason, confidence, and cryptographic suggestion_id:
- ✅ 19A: `pradyos/core/intent_engine.py` — `IntentSuggestion` dataclass (`suggestion_id` uuid4 hex, `action`, `target`, `reason`, `confidence`, `ts`, `to_dict()`). `IntentEngine` class: thread-safe `load_rules()` / `get_rules()` (independent copy), `suggest()` evaluating four conditions — `graph_nodes_gt`, `error_span_rate_gt`, `active_campaigns_lt`, `ledger_events_gt`; unknown conditions silently skipped.
- ✅ 19B: `pradyos/sovereign_web.py` — patched to add optional `intent` param to `create_app()`; `GET /api/v1/intent/rules` returns `{rules, count}`; `POST /api/v1/intent/rules` body `{rules:[...]}` returns `{loaded}`; `POST /api/v1/intent/suggest` body `{graph_stats, active_campaigns, recent_spans, recent_entries}` returns `{suggestions, count}`. Safe empty responses when no intent injected.
- ✅ 19C: `tests/test_intent_engine.py` — 20 unit tests covering all four conditions (fire and no-fire cases), mutation-safe copy semantics, suggestion field correctness, uuid hex id, approximate ts, `to_dict()` keys, unknown condition skip, and empty-list clear.
- ✅ 19D: `tests/test_intent_web.py` — 10 FastAPI TestClient tests for all three intent endpoints including round-trip POST→GET rules verification and no-intent safe-empty responses.
- ✅ 19E: `scripts/prove.py` updated with both new test modules (55 total).
- ✅ 19F: README Phase Map updated; Phase 20 planned.

**Phase 20 — Complete.** All 57 test modules green. Sovereign Audit Trail UI — a self-contained dark-themed HTML page served at `/audit` that fetches live data from three API endpoints (`/api/v1/ledger`, `/api/v1/telemetry`, `/api/v1/intent/suggest`) and auto-refreshes every 10 seconds; pure HTML/CSS/JS, no external dependencies:
- ✅ 20A: `pradyos/sovereign/audit_ui.py` — `AUDIT_HTML` constant (complete self-contained HTML page) and `build_audit_html() -> str` function. Three sections: **Event Ledger** (seq#, timestamp, service, event, payload, hash), **Telemetry Spans** (span_id, trace_id, name, service, start, duration_ms, status), **Intent Suggestions** (action, priority, reason, rule, params). Each section shows up to 20 most-recent items; graceful "No data" when APIs return empty. Auto-refresh every 10 s via `setInterval`. Dark theme consistent with the existing dashboard.
- ✅ 20B: `pradyos/sovereign_web.py` — patched via script to add `from pradyos.sovereign.audit_ui import build_audit_html` and `GET /audit` endpoint returning `HTMLResponse(build_audit_html())`. `DASHBOARD_HTML` constant untouched.
- ✅ 20C: `tests/test_audit_ui.py` — 10 unit tests: non-empty return, DOCTYPE, ledger/telemetry/intent API URLs, all three section headings, auto-refresh logic, idempotence.
- ✅ 20D: `tests/test_audit_web.py` — 10 FastAPI TestClient tests: HTTP 200, Content-Type text/html, DOCTYPE, all three section headings, all three API URL references, idempotence.
- ✅ 20E: `scripts/prove.py` updated with both new test modules (57 total).
- ✅ 20F: README Phase Map updated; Phase 21 planned.

**Phase 21 — Planned.** Sovereign Config Hot-Reload — a file-watcher that monitors a YAML config file for changes and hot-reloads intent engine rules, scheduler jobs, and policy rules without restarting the server; exposes `/api/v1/config/reload` and `/api/v1/config/status`.

**Phase 15 — Complete.** All 47 test modules green. Sovereign Scheduler — cron-style recurring campaigns with priority queues and SLA-aware routing:
- ✅ 15A: `pradyos/sovereign/scheduler.py` — `SovereignScheduler` class with
  injectable `clock` for deterministic testing. Pure-stdlib 5-field cron parser
  supporting `*`, `*/N`, and single-integer fields for minute/hour/dom/month/dow.
  `next_run_after(cron_expr, after_ts)` scans minute-by-minute in UTC.
  `add_job()` stores job dicts with `job_id`, `cron_expr`, `campaign_spec`,
  `priority`, `sla_seconds`, `next_run`, `enabled`. `remove_job()` / `enable_job()`
  / `disable_job()` return bool. `tick()` fires all enabled jobs whose
  `next_run <= clock()`, publishes `"scheduler.job.fired"` bus events, advances
  `next_run`, and returns the list of fired job_ids. `start()` / `stop()` manage a
  daemon background thread; both are idempotent. Thread-safe via `threading.Lock`.
- ✅ 15B: `pradyos/sovereign_web.py` — five new endpoints wired via optional
  `scheduler` param in `create_app()`: `GET /api/v1/scheduler/jobs`,
  `POST /api/v1/scheduler/jobs`, `DELETE /api/v1/scheduler/jobs/{job_id}`,
  `POST /api/v1/scheduler/jobs/{job_id}/enable`,
  `POST /api/v1/scheduler/jobs/{job_id}/disable`. All return HTTP 200; safe
  empty responses when scheduler not injected.
- ✅ 15C: `tests/test_sovereign_scheduler.py` — 20 unit tests covering all
  scheduler methods, cron parsing, clock injection, bus event payload, copy
  isolation, idempotent start/stop, and job-id collision overwrite.
- ✅ 15D: `tests/test_scheduler_web.py` — 10 FastAPI TestClient tests:
  GET/POST/DELETE/enable/disable endpoints, required keys, GET-after-POST
  reflection, and response shape.
- ✅ 15E: `scripts/prove.py` updated with both new test modules (47 total).
- ✅ 15F: README Phase Map updated; Phase 16 planned.

**Phase 14 — Complete.** All 46 test modules green. Policy engine —
IMPERIUM enforces Sovereign-configured rules at dispatch time:
- ✅ 14A: `pradyos/imperium/policy_engine.py` — `PolicyEngine` class
  (pure — no bus, no kernel imports) with `load()` / `get_rules()` /
  `evaluate()` returning a `PolicyVerdict(allowed, reason)` dataclass.
  Three rule types: **constitutional_guard** (unconditional block),
  **rate_limit** (timestamp-list counter pruned by `time.time()`),
  **approval_required** (allowed=True; enforcement delegated to Sovereign).
  Match semantics: empty dict matches all tasks; string values use substring
  containment; all keys must satisfy for a rule to fire. Thread-safe via
  `threading.Lock`. `PolicyViolationError` defined in same module.
- ✅ 14B: `pradyos/imperium/kernel.py` — `PolicyEngine` injected into
  `ImperiumKernel.__init__` as optional `policy_engine` param (falls back
  to permissive engine). `_run_record()` calls `policy_engine.evaluate()`
  before the constitutional gate; raises `PolicyViolationError` if blocked.
- ✅ 14C: `pradyos/sovereign_web.py` — `GET /api/v1/policy/rules` returns
  `{"rules": [...]}` (200); `POST /api/v1/policy/rules` body
  `{"rules": [...]}` calls `policy_engine.load()`, returns
  `{"loaded": N}` (200). Wired via new `policy_engine` param in
  `create_app()`. Falls back to empty rules list when not injected.
- ✅ 14D: `tests/test_policy_engine.py` — 20 unit tests covering all rule
  types, match semant