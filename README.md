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

**Phase 21 — Complete.** All 59 test modules green. Sovereign Config Hot-Reload — a file-watcher that monitors a YAML/JSON config file for changes and hot-reloads intent engine rules, scheduler jobs, and policy rules without restarting the server:
- ✅ 21A: `pradyos/core/config_hot_reload.py` — `ReloadResult` dataclass with `to_dict()`; `ConfigHotReloader` class with `load()`, `start()`, `stop()`, `last_result()`, `status()`. Background daemon thread polls `config_path` every `poll_interval` seconds; reloads on mtime change. Uses `yaml.safe_load` if PyYAML present, falls back to `json.loads` (stdlib-only). Each config section (`intent_rules`, `scheduler_jobs`, `policy_rules`) is optional; missing sections and `None` components are silently skipped. Returns `ReloadResult(success=False, error=…)` on any exception.
- ✅ 21B: `pradyos/sovereign_web.py` — patched via script to add `config_reloader` param to `create_app()` and two new endpoints: `GET /api/v1/config/status` returns `reloader.status()` (or stub dict when not injected); `POST /api/v1/config/reload` calls `reloader.load()` and returns `result.to_dict()`. `DASHBOARD_HTML` constant untouched.
- ✅ 21C: `tests/test_config_hot_reload.py` — 20 unit tests covering `ReloadResult.to_dict()` keys, `load()` success/failure paths, all three config sections, missing sections, `None` components, file-not-found, invalid JSON, `status()` keys, `_running` transitions, `last_result()` lifecycle, start/stop cycle, changes list type and content.
- ✅ 21D: `tests/test_config_reload_web.py` — 10 FastAPI TestClient tests: HTTP 200 for both endpoints, required response keys, no-reloader stubs, valid-reloader success, error=None on success, config_path reflection, changes list type.
- ✅ 21E: `scripts/prove.py` updated with both new test modules (59 total).
- ✅ 21F: README Phase Map updated; Phase 22 planned.

**Phase 22 — Complete.** All 61 test modules green. Sovereign Metrics Dashboard — Prometheus-compatible `/metrics` endpoint with OS-level counters:
- ✅ 22A: `pradyos/core/metrics_registry.py` — `MetricsRegistry` class with thread-safe `increment()`, `set()`, `get()`, `get_all()`, `reset()`, `render_prometheus()`. Pre-registers 8 counters at 0: `pradyos_campaigns_run_total`, `pradyos_tasks_dispatched_total`, `pradyos_errors_total`, `pradyos_ledger_entries_total`, `pradyos_intent_suggestions_total`, `pradyos_policy_violations_total`, `pradyos_scheduler_jobs_fired_total`, `pradyos_config_reloads_total`. Prometheus text export sorted by name; integers rendered without decimal point. Thread-safe via `threading.Lock`. Zero external dependencies.
- ✅ 22B: `pradyos/sovereign_web.py` — patched via script to add `metrics` optional param to `create_app()` and two new endpoints: `GET /metrics` returns Prometheus plain-text (`text/plain; version=0.0.4`) or empty string when not injected; `GET /api/v1/metrics` returns `registry.get_all()` as JSON or `{}` when not injected. `DASHBOARD_HTML` constant untouched.
- ✅ 22C: `tests/test_metrics_registry.py` — 20 unit tests covering init, get/increment/set/reset, get_all mutation safety, render_prometheus format (# HELP/# TYPE, sorted output, integer vs float rendering, trailing newline), all 8 pre-registered names, and thread safety (100 concurrent increments).
- ✅ 22D: `tests/test_metrics_web.py` — 10 FastAPI TestClient tests: HTTP 200 for both endpoints, Content-Type text/plain, non-empty body, # HELP in body, pre-registered name in body, JSON object response, at least one key after increment, no-metrics stub returns 200/empty/`{}`.
- ✅ 22E: `scripts/prove.py` updated with both new test modules (61 total).
- ✅ 22F: README Phase Map updated; Phase 23 planned.

**Phase 23 — Complete.** All 63 test modules green. Sovereign Rate-Limit Shield — sliding-window, in-memory per-(client_id, endpoint) rate limiter with injectable clock for deterministic testing:
- ✅ 23A: `pradyos/core/rate_limiter.py` — `RateLimitResult` dataclass with `to_dict()` + `RateLimiter` class. Sliding-window counter prunes timestamps older than `window_secs`. `check()` records hits when allowed, does NOT record when denied; returns `retry_after` seconds until reset. `set_rule()` / `get_rules()` for per-endpoint overrides. `reset(client_id, endpoint?)` clears timestamps. `status()` reports active_clients, total_hits, rules. Thread-safe via `threading.Lock`. Zero external dependencies.
- ✅ 23B: `pradyos/sovereign_web.py` — patched via script to add `rate_limiter` optional param to `create_app()` and three new endpoints: `GET /api/v1/ratelimit/status` returns limiter.status() or stub; `POST /api/v1/ratelimit/rules` sets per-endpoint rule; `POST /api/v1/ratelimit/check` evaluates a (client_id, endpoint) pair and returns full RateLimitResult dict. `DASHBOARD_HTML` constant untouched.
- ✅ 23C: `tests/test_rate_limiter.py` — 20 unit tests covering init, check result type, allowed/denied logic, hit recording, sliding window pruning with injectable clock, set_rule/get_rules mutation safety, reset by client and by endpoint, status keys and counts, to_dict keys, retry_after=None/float, 10-hit boundary, cross-endpoint and cross-client independence.
- ✅ 23D: `tests/test_rate_limit_web.py` — 10 FastAPI TestClient tests: HTTP 200 for all endpoints, required keys in responses, allowed=True under limit, stub behaviour when no limiter injected, rule-then-check enforcement.
- ✅ 23E: `scripts/prove.py` updated with both new test modules (63 total).
- ✅ 23F: README Phase Map updated; Phase 24 planned.

**Phase 24 — Complete.** All 65 test modules green. Sovereign Health Scorecard — a composite health score (0–100) engine with thread-safe component registry, weighted-average scoring, and A/B/C/D/F grading:
- ✅ 24A: `pradyos/core/health_scorecard.py` — `ComponentScore` and `HealthReport` dataclasses; `HealthScorecard` class with `register()`, `update()` (clamped 0–100, auto-registers), `get_report()` (weighted average, grade), `reset()`. Thread-safe via `threading.Lock`.
- ✅ 24B: `pradyos/sovereign_web.py` patched — `scorecard` optional param added to `create_app()`; `GET /api/v1/health/score` returns composite report; `POST /api/v1/health/update` accepts name/score/details and calls `scorecard.update()`. Safe empty responses when scorecard not injected.
- ✅ 24C: `tests/test_health_scorecard.py` — 20 unit tests covering init, default report, grade boundaries (A/B/C/D/F), clamping, auto-register, explicit weights, weighted average, `reset()`, `to_dict()` keys, details default, and 50-thread concurrency.
- ✅ 24D: `tests/test_health_web.py` — 10 FastAPI TestClient tests covering GET/POST endpoints, no-scorecard fallbacks (score=100, updated=false), update-then-get round-trip, and grade A/F scenarios.
- ✅ 24E: `scripts/prove.py` updated to 65 modules.
- ✅ 24F: README Phase Map updated; Phase 25 planned.

**Phase 25 — Complete.** All 67 test modules green. Sovereign Audit Replay Engine — a time-travel state reconstructor that replays the append-only audit ledger forward from genesis to reconstruct PradyOS state at any past timestamp:

- ✅ 25A: `pradyos/core/audit_replay.py` — `AuditReplayEngine` with `ReplayEntry` / `ReplaySnapshot` dataclasses; thread-safe via `threading.Lock`; supports external ledger or internal entry list.
- ✅ 25B: `GET /api/v1/audit/replay?at=<unix_ts>` endpoint wired into `sovereign_web.py`; graceful no-op when `replay_engine=None`.
- ✅ 25C: `tests/test_audit_replay.py` — 20 unit tests (init, filtering, sorting, state merge, thread safety, ledger modes).
- ✅ 25D: `tests/test_audit_replay_web.py` — 10 FastAPI TestClient tests for the `/api/v1/audit/replay` endpoint.
- ✅ 25E: `scripts/prove.py` updated to 67 modules.
- ✅ 25F: README Phase Map updated; Phase 26 planned.

**Phase 26 — Complete.** All 69 test modules green. Sovereign Plugin Sandbox — a lightweight plugin loader that discovers, validates, and hot-loads Python modules from a `plugins/` directory at runtime:

- ✅ 26A: `pradyos/core/plugin_sandbox.py` — `PluginManifest` / `LoadedPlugin` dataclasses; `PluginSandbox` with `discover()`, `load()`, `reload_all()`, `get_plugins()`, `unload()`, `status()`; thread-safe via `threading.Lock`.
- ✅ 26B: `GET /api/v1/plugins` and `POST /api/v1/plugins/reload` wired into `sovereign_web.py`; graceful no-op when `plugin_sandbox=None`.
- ✅ 26C: `tests/test_plugin_sandbox.py` — 20 unit tests (init, discover, load success/error, reload_all, get_plugins, unload, status, to_dict, thread safety with 20 concurrent loads).
- ✅ 26D: `tests/test_plugin_web.py` — 10 FastAPI TestClient tests for plugin list and reload endpoints.
- ✅ 26E: `scripts/prove.py` updated to 69 modules.
- ✅ 26F: README Phase Map updated; Phase 27 planned.

**Phase 27 — Complete.** All 71 test modules green. Sovereign Event Bus Inspector — a live diagnostic ring buffer for all event bus messages:

- ✅ 27A: `pradyos/core/bus_inspector.py` — `BusEvent` dataclass with `to_dict()`; `BusInspector` with `collections.deque` ring buffer (`max_size=500`), `record()`, `get_events()` (topic filter, limit, offset), `get_stats()`, and `clear()`; thread-safe via `threading.Lock`.
- ✅ 27B: `pradyos/sovereign_web.py` — `GET /api/v1/bus/events` (query params: topic, limit, offset) and `GET /api/v1/bus/stats` wired into `create_app(bus_inspector=...)`; graceful no-op when `bus_inspector=None`.
- ✅ 27C: `tests/test_bus_inspector.py` — 20 unit tests (init, record, get_events filtering, stats, overflow, clear, to_dict, defaults, thread safety with 100 concurrent records).
- ✅ 27D: `tests/test_bus_inspector_web.py` — 10 FastAPI TestClient tests for bus events and stats endpoints.
- ✅ 27E: `scripts/prove.py` updated to 71 modules.
- ✅ 27F: README Phase Map updated; Phase 28 planned.

**Phase 28 — Complete.** All 73 test modules green. Sovereign Decision Journal — an append-only JSONL decision log with cryptographic chaining (each entry embeds the SHA-256 content_hash of the previous entry as prev_hash, genesis uses "0"*64); thread-safe DecisionJournal with file or memory-only mode; GET /api/v1/decisions (paginated, filterable by agent_id/decision_type) and POST /api/v1/decisions (record a new decision with agent_id, decision_type, rationale, outcome); verify_chain() walks the full chain and detects any tampering; stdlib only:

- ✅ 28A: `pradyos/core/decision_journal.py` — DecisionEntry dataclass + DecisionJournal with crypto-chain
- ✅ 28B: `pradyos/sovereign_web.py` patched — GET/POST /api/v1/decisions wired in
- ✅ 28C: `tests/test_decision_journal.py` — 20 unit tests (chain, persistence, filters, thread safety)
- ✅ 28D: `tests/test_decision_web.py` — 10 FastAPI endpoint tests
- ✅ 28E: `scripts/prove.py` — 73 test modules registered
- ✅ 28F: README Phase Map updated; Phase 29 planned.

**Phase 29 — Complete.** All 75 test modules green. Sovereign Capability Registry — a self-describing runtime registry where every PradyOS module registers its own capabilities (name, version, provided_apis, consumed_apis, status); enables the OS to introspect its own feature surface at runtime; stdlib only:

- ✅ 29A: `pradyos/core/capability_registry.py` — `Capability` dataclass with `to_dict()`; `CapabilityRegistry` with `register()`, `get()`, `list_all()`, `update_status()`, `unregister()`, `summary()` (api_surface counts unique provided_apis); thread-safe via `threading.Lock`.
- ✅ 29B: `pradyos/sovereign_web.py` patched — `GET /api/v1/capabilities` (full list + summary), `POST /api/v1/capabilities` (register/overwrite), `GET /api/v1/capabilities/{name}` (single lookup with 404) wired into `create_app(capability_registry=...)`.
- ✅ 29C: `tests/test_capability_registry.py` — 20 unit tests (init, register, get, list_all sorted, overwrite, update_status, unregister, summary keys/counts/api_surface dedup, defaults, to_dict, thread safety with 50 concurrent registrations).
- ✅ 29D: `tests/test_capability_web.py` — 10 FastAPI TestClient tests for all 3 endpoints including no-registry fallbacks, 404 handling, and summary count propagation.
- ✅ 29E: `scripts/prove.py` — 75 test modules registered.
- ✅ 29F: README Phase Map updated; Phase 30 planned.

**Phase 30 — Complete.** All 77 test modules green. Sovereign Watchpoint System — an assertion-based runtime monitor where any module registers named threshold watchpoints (gt, lt, gte, lte, eq) against named numeric metrics; when a watchpoint fires it emits a structured alert with severity (info/warn/critical) and appends it to a thread-safe ring-buffer alert log; stdlib only:

- ✅ 30A: `pradyos/core/watchpoint.py` — `Watchpoint` and `Alert` dataclasses with `to_dict()`; `WatchpointSystem` with `register()` (validates operator + severity), `check()` (evaluates all enabled matching watchpoints), `get_alerts()` (filter by name/severity, limit), `get_watchpoints()` (sorted by name), `disable()`, `enable()`, `status()`; thread-safe via `threading.Lock`; ring buffer via `collections.deque(maxlen=max_alerts)` with `_total_alerts` counter.
- ✅ 30B: `pradyos/sovereign_web.py` patched — `GET /api/v1/watchpoints` (list + status), `POST /api/v1/watchpoints` (register), `POST /api/v1/watchpoints/check` (evaluate metric value) wired into `create_app(watchpoint_system=...)`.
- ✅ 30C: `tests/test_watchpoint.py` — 20 unit tests (init, register, all 5 operators, disabled skip, disable/enable, get_alerts oldest-first/filter/limit, status keys, thread safety with 50 concurrent checks).
- ✅ 30D: `tests/test_watchpoint_web.py` — 10 FastAPI TestClient tests for all 3 endpoints including no-system fallbacks and end-to-end fire-and-check.
- ✅ 30E: `scripts/prove.py` — 77 test modules registered.
- ✅ 30F: README Phase Map updated; Phase 31 planned.

**Phase 31 — Complete.** All 79 test modules green. Sovereign Signal Aggregator — a time-series ring buffer that collects named numeric signals from any module, stores them per-signal in a `collections.deque` (max_total cap), and computes live stats (min, max, mean, population stddev) on demand; stdlib only, no numpy:

- ✅ 31A: `pradyos/core/signal_aggregator.py` — `SignalPoint` dataclass with `to_dict()`; `SignalAggregator` with `record()` (auto-creates per-signal deque, supports custom timestamp), `get()` (last-N oldest-first), `list_signals()` (sorted by name, count + latest), `stats()` (min/max/mean/population-stddev, returns None for unknown signal); thread-safe via `threading.Lock`.
- ✅ 31B: `pradyos/sovereign_web.py` patched — `GET /api/v1/signals` (list all), `POST /api/v1/signals` (record point), `GET /api/v1/signals/{name}` (last N points + stats, never 404) wired into `create_app(signal_aggregator=...)`.
- ✅ 31C: `tests/test_signal_aggregator.py` — 20 unit tests (init, record, get oldest-first/limit/all, list_signals sorted/keys/latest, stats None/keys/min-max/mean/stddev/single-point, custom timestamp, thread safety 50 concurrent, count consistency).
- ✅ 31D: `tests/test_signal_web.py` — 10 FastAPI TestClient tests for all 3 endpoints including no-aggregator fallbacks, end-to-end POST→GET, and unknown-signal 200 with empty points.
- ✅ 31E: `scripts/prove.py` — 79 test modules registered.
- ✅ 31F: README Phase Map updated; Phase 32 planned.

**Phase 32 — Complete.** All 81 test modules green. Sovereign Snapshot Store — versioned, namespaced JSON snapshot persistence with optional JSONL file backend; each (namespace, key) pair accumulates auto-incrementing version history; thread-safe; reloads from disk on re-init; stdlib only:

- ✅ 32A: `pradyos/core/snapshot_store.py` — `Snapshot` dataclass with `to_dict()`; `SnapshotStore` with `save()` (auto-increment version, optional JSONL append), `get()` (latest or specific version), `list_keys()` (sorted, with versions/latest_version/latest_saved_at), `delete()` (memory-only tombstone), `count()` (global or namespace-scoped); memory-only mode when `base_dir=None`; thread-safe via `threading.Lock`.
- ✅ 32B: `pradyos/sovereign_web.py` patched — `GET /api/v1/snapshots/{namespace}` (list keys), `POST /api/v1/snapshots/{namespace}/{key}` (save), `GET /api/v1/snapshots/{namespace}/{key}` (retrieve, ?version=N, 404 if missing), `DELETE /api/v1/snapshots/{namespace}/{key}` (remove, 404 if missing) wired into `create_app(snapshot_store=...)`.
- ✅ 32C: `tests/test_snapshot_store.py` — 20 unit tests (init, save, version increment, get latest/specific/unknown, list_keys sorted/fields/count/unknown-ns, delete/unknown, count global/scoped, JSONL persist, reload, reloaded-get, thread-safety 50 concurrent saves with no version gaps).
- ✅ 32D: `tests/test_snapshot_web.py` — 10 FastAPI TestClient tests for all 4 endpoints including no-store fallbacks, 404 for unknown key, version=2 on second save, and end-to-end POST→GET→DELETE.
- ✅ 32E: `scripts/prove.py` — 81 test modules registered.
- ✅ 32F: README Phase Map updated; Phase 33 planned.

**Phase 33 — Complete.** All 83 test modules green. Sovereign Correlation Engine — temporal Pearson correlation between named SignalAggregator signals using nearest-neighbour timestamp pairing; stdlib only, no numpy:

- ✅ 33A: `pradyos/core/correlation_engine.py` — `CorrelationResult` dataclass with `to_dict()` (NaN → None for JSON); `CorrelationEngine.correlate()` filters by window, pairs by nearest timestamp, computes population-stddev Pearson r, returns qualitative label (strong-positive ≥0.7, moderate-positive ≥0.4, weak >-0.4, moderate-negative >-0.7, strong-negative); handles <2 samples or zero-stddev → NaN with label="weak".
- ✅ 33B: `pradyos/sovereign_web.py` patched — `GET /api/v1/correlate?signal_a=X&signal_b=Y&window=N` and `POST /api/v1/correlate` wired into `create_app(correlation_engine=...)`.
- ✅ 33C: `tests/test_correlation_engine.py` — 20 unit tests (init, return type, no-overlap, perfect positive, perfect negative, constant→nan, single-point→nan, window filter, window=0, label thresholds, to_dict keys, computed_at, window_secs, names, nearest-neighbour pairing, read-only, large dataset 1000 pts).
- ✅ 33D: `tests/test_correlation_web.py` — 10 FastAPI TestClient tests (no-engine/missing-params for GET+POST, valid GET/POST 200, all fields present, window=0→sample_size=0, identical signals→coefficient=1.0).
- ✅ 33E: `scripts/prove.py` — 83 test modules registered.
- ✅ 33F: README Phase Map updated; Phase 34 planned.

**Phase 34 — Complete.** All 85 test modules green. Sovereign Integration Bus — cross-module wiring layer connecting SignalAggregator, WatchpointSystem, DecisionJournal, BusInspector, CapabilityRegistry, and HealthScorecard; all dependencies optional; stdlib only:

- ✅ 34A: `pradyos/core/integration_bus.py` — `SovereignBus` with three wires: `record_signal()` calls aggregator.record + watchpoint.check + journal.record on alert; `record_bus_event()` calls bus_inspector.record + aggregator.record("bus.{topic}", 1.0); `update_capability()` calls capability_registry.update_status + health_scorecard.update(name, 0) on "degraded"; `status()` returns wired-dict + wire_count.
- ✅ 34B: `pradyos/sovereign_web.py` patched — `GET /api/v1/integration/status` wired into `create_app(integration_bus=...)`.
- ✅ 34C: `tests/test_integration_bus.py` — 20 unit tests (init, status structure, wire counts, all three wires, no-crash when deps missing, end-to-end 6-module alert flow).
- ✅ 34D: `tests/test_integration_web.py` — 10 FastAPI TestClient tests (no-bus fallback, wire_count 0/1/6, all-6 keys, boolean values, wired reflects actual state).
- ✅ 34E: `scripts/prove.py` — 85 test modules registered.
- ✅ 34F: README Phase Map updated; Phase 35 planned.

**Phase 35 — Complete.** All 87 test modules green. Sovereign Autonomous Reactor — rule-based reaction engine that fires when DecisionJournal records matching entries; wired into SovereignBus so watchpoint → journal → reactor fires inline; stdlib only:

- ✅ 35A: `pradyos/core/reactor.py` — `ReactorRule` + `ReactionEvent` dataclasses with `to_dict()`; `ReactorEngine` with `add_rule()` (uuid4 rule_id, default context_filter={}), `remove_rule()`, `list_rules()` (sorted by created_at), `react(entry)` (decision_type exact match + context_filter substring match against rationale), `get_log(limit)`, `count()`; thread-safe via `threading.Lock`; ring buffer log (max 1000).
- ✅ 35B: `pradyos/sovereign_web.py` patched — `GET/POST /api/v1/reactor/rules`, `DELETE /api/v1/reactor/rules/{rule_id}` (404 if missing), `GET /api/v1/reactor/log?limit=N` wired into `create_app(reactor_engine=...)`. ALSO updated `pradyos/core/integration_bus.py` — `SovereignBus` gained `reactor_engine` param; WIRE 1 now calls `reactor_engine.react(entry)` after journal.record(), so watchpoint→journal→reactor fires automatically.
- ✅ 35C: `tests/test_reactor.py` — 20 unit tests (init, add_rule fields/unique-ids/default-filter, remove_rule, list_rules sorted, react no-rules/match/filter-type/substring/empty-filter/no-match, log append, get_log limit, count, thread safety 50 concurrent reacts).
- ✅ 35D: `tests/test_reactor_web.py` — 11 tests covering all 4 endpoints (no-reactor fallback, response shape, 404 on delete, full POST→react→log flow) + 1 end-to-end test that wires SovereignBus with watchpoint+journal+reactor and verifies a single record_signal() call triggers the full chain.
- ✅ 35E: `scripts/prove.py` — 87 test modules registered.
- ✅ 35F: README Phase Map updated; Phase 36 planned.

**Phase 36 — Complete.** All 89 test modules green. Sovereign State Persistence — `StateManager` wraps the SnapshotStore with module-scoped helpers and ordered shutdown hooks; on shutdown, all hooks fire in registration order and the result list captures `name:ok` or `name:error:...` per hook; stdlib only:

- ✅ 36A: `pradyos/core/state_manager.py` — `StateManager` with `register_module()` (dedup), `save_state()`/`load_state()` (return None when no store), `register_hook(name, fn)` (preserves order), `shutdown()` (fires hooks in order, swallows exceptions into result strings, returns list), `status()` (store_connected, registered_modules, hook_count); thread-safe via `threading.Lock`.
- ✅ 36B: `pradyos/sovereign_web.py` patched — `POST /api/v1/os/shutdown` (hook results), `GET /api/v1/os/state/{module}` (list keys), `GET /api/v1/os/state/{module}/{key}?version=N` (load, 404 if missing), `POST /api/v1/os/state/{module}/{key}` (save), `GET /api/v1/os/status` wired into `create_app(state_manager=...)`.
- ✅ 36C: `tests/test_state_manager.py` — 20 unit tests (init, register_module dedup, save/load None when no store, version=N, register_hook, shutdown returns list/ok/error continues/order/empty, status keys/connection/modules/hook_count).
- ✅ 36D: `tests/test_state_web.py` — 10 FastAPI TestClient tests (status no-sm, shutdown 200/no-sm/hook fires, state list/no-sm, save error no-sm, get unknown 404, full save→load flow).
- ✅ 36E: `scripts/prove.py` — 89 test modules registered.
- ✅ 36F: README Phase Map updated; Phase 37 planned.

**Phase 37 — Complete.** All 91 test modules green. Sovereign Self-Healing Monitor — `HealingMonitor` polls `HealthScorecard.get_report()` on demand (via `check_and_heal()`); for each registered component with score below its threshold, fires its repair callable (exceptions swallowed) and records a `HealingEvent`; stdlib only:

- ✅ 37A: `pradyos/core/healing_monitor.py` — `HealingComponent` + `HealingEvent` dataclasses with `to_dict()`; `HealingMonitor` with `register(name, threshold, action, repair_fn)`, `unregister()` (cleans both dicts), `list_components()` (sorted), `check_and_heal()` (converts `HealthReport.components` list-of-ComponentScore via helper to {name: score}, skips uninitialised components, swallows repair exceptions, captures before/after scores), `get_log(limit)`, `count()`; thread-safe via `threading.Lock`; ring buffer log (max 500).
- ✅ 37B: `pradyos/sovereign_web.py` patched — `GET /api/v1/healer/components`, `POST /api/v1/healer/check`, `GET /api/v1/healer/log?limit=N` wired into `create_app(healing_monitor=...)`.
- ✅ 37C: `tests/test_healing_monitor.py` — 20 unit tests (init, register/unregister/list_components, check_and_heal empty/above-threshold/below-threshold/no-scorecard/missing-in-report/exception-swallowed, event fields, log append, score_before correctness, repair_fn invocation, get_log limit, count, thread safety 20 concurrent calls).
- ✅ 37D: `tests/test_healing_web.py` — 10 FastAPI TestClient tests (no-monitor fallbacks for all 3 endpoints, above-threshold no-heal, below-threshold one-event, log reflects healing, components reflects registrations).
- ✅ 37E: `scripts/prove.py` — 91 test modules registered.
- ✅ 37F: README Phase Map updated; Phase 38 planned.

**Phase 38 — Complete.** All 93 test modules green. Sovereign Scheduler — tick-driven task engine; no background threads — caller invokes `tick()` as the heartbeat; each due task runs inline and produces a `TaskRun` record (success / error / duration_ms); stdlib only:

- ✅ 38A: `pradyos/core/scheduler.py` — `ScheduledTask` + `TaskRun` dataclasses with `to_dict()`; `TaskScheduler` with `register()` (overwrites on dupe, next_run_at=now+interval, last_run=None), `unregister()`/`enable()`/`disable()`, `list_tasks()` (sorted), `tick(now=None)` (skips disabled + not-due, captures exceptions, updates last_run/next_run_at, appends TaskRun), `get_log(limit)`, `count()`; thread-safe via `threading.Lock`; ring buffer (max 1000).
- ✅ 38B: `pradyos/sovereign_web.py` patched — `GET/POST /api/v1/scheduler/tasks`, `DELETE /api/v1/scheduler/tasks/{name}` (404 if missing), `POST /api/v1/scheduler/tick` wired into `create_app(task_scheduler=...)`. New endpoints coexist with the existing Phase 15 `/api/v1/scheduler/jobs` endpoints; module imported as `CoreTaskScheduler` alias to avoid symbol collision.
- ✅ 38C: `tests/test_task_scheduler.py` — 20 unit tests (init, register fields/overwrite, unregister, enable/disable, disable-prevents-tick, list_tasks sorted, tick empty/fires/updates state/success/error/log-append, get_log limit, count).
- ✅ 38D: `tests/test_task_scheduler_web.py` — 10 FastAPI TestClient tests (no-scheduler fallbacks for all 4 endpoints, POST response shape, DELETE 200 + 404, full register→force-due→tick→log flow).
- ✅ 38E: `scripts/prove.py` — 93 test modules registered.
- ✅ 38F: README Phase Map updated; Phase 39 planned.

**Phase 39 — Complete.** All 95 test modules green. Sovereign Memory Layer — `MemoryStore` provides TTL-aware keyed memory with tag search and optional SnapshotStore-backed persistence; entries reload from disk on init (expired entries discarded); stdlib only:

- ✅ 39A: `pradyos/core/memory_store.py` — `MemoryEntry` dataclass with `to_dict()` and `is_expired()`; `MemoryStore` with `store()` (upsert preserves `created_at`, persists via snapshot_store if set), `recall()` (lazy-evicts expired), `search(tag)` (sorted, lazy-evicts), `forget()`, `expire()` (returns count), `count()` (raw count, no eviction); thread-safe via `threading.Lock`.
- ✅ 39B: `pradyos/sovereign_web.py` patched — `GET /api/v1/memory/search?tag=X`, `POST /api/v1/memory/expire`, `POST/GET/DELETE /api/v1/memory/{key}` wired into `create_app(memory_store=...)`. `search` and `expire` routes registered BEFORE `/{key}` to avoid path-param capture.
- ✅ 39C: `tests/test_memory_store.py` — 20 unit tests (init, store new/upsert/created_at preservation, recall present/unknown/expired with eviction, search match/empty/exclude-expired/sorted, forget, expire count/keeps-non-expired, count includes-expired, snapshot persist & reload).
- ✅ 39D: `tests/test_memory_web.py` — 10 FastAPI TestClient tests (POST 200/no-store/fields, GET 200/404, DELETE 200/404, search, expire count, full TTL→expire→404 flow).
- ✅ 39E: `scripts/prove.py` — 95 test modules registered.
- ✅ 39F: README Phase Map updated; Phase 40 planned.

**Phase 40 — Complete.** All 97 test modules green. Sovereign OS Control Plane — the final integration layer. `ControlPlane` wraps all 11 OS modules and provides unified introspection + a single tick heartbeat that drives the scheduler, healer, and reactor in sequence; stdlib only:

- ✅ 40A: `pradyos/core/control_plane.py` — `VERSION = "0.40.0"`; `ControlPlane` with `uptime()` (seconds since init), `_safe_summary()` (handles None/missing-method/exception/non-dict-result), `status()` (returns `{os_version, uptime_seconds, modules: {11 names → {present, summary}}}`), `tick()` (runs `task_scheduler.tick()` → `healing_monitor.check_and_heal()` → `reactor_engine.react({})`, each wrapped in try/except). Introspection map: health_scorecard→get_report, signal_aggregator→list_signals, task_scheduler/memory_store/healing_monitor/snapshot_store/reactor_engine→count, state_manager/watchpoint_system/integration_bus→status, correlation_engine→{} (no method).
- ✅ 40B: `pradyos/sovereign_web.py` patched — `GET /api/v1/os/control` (unified status), `POST /api/v1/os/tick` (heartbeat) wired into `create_app(control_plane=...)`. **Deviation:** Phase 36 already owns `GET /api/v1/os/status` — the new endpoint uses `/api/v1/os/control` instead to preserve Phase 36 tests.
- ✅ 40C: `tests/test_control_plane.py` — 20 unit tests (init, uptime, status os_version/uptime/keys/all-11-modules/present/summary, _safe_summary None/works/raises, tick keys/empty/scheduler/healer/exception-swallowing/list, real-modules integration).
- ✅ 40D: `tests/test_control_web.py` — 10 FastAPI TestClient tests covering both endpoints and all 11 module names in the modules dict.
- ✅ 40E: `scripts/prove.py` — 97 test modules registered.
- ✅ 40F: README Phase Map updated; Phase 41 planned.

**Phase 41 — Complete.** All 99 test modules green. Sovereign Heartbeat Loop — async background driver that calls `ControlPlane.tick()` on a fixed interval, transforming the OS from on-demand to self-driving; FastAPI startup/shutdown lifecycle hooks auto-start and auto-stop the loop; stdlib + asyncio only:

- ✅ 41A: `pradyos/core/heartbeat.py` — `HeartbeatConfig` (interval_seconds default 5.0, max_ticks optional cap), `HeartbeatLoop` with `start()` (idempotent), `stop()` (graceful with timeout fallback to cancel), `_loop()` (swallows tick exceptions, increments thread-safe counter, stops at max_ticks), `status()`; thread-safe via `threading.Lock` on `tick_count`.
- ✅ 41B: `pradyos/sovereign_web.py` patched — `@app.on_event("startup")` auto-calls `heartbeat.start()`, `@app.on_event("shutdown")` calls `heartbeat.stop()`; `GET /api/v1/heartbeat/status` (status dict), `POST /api/v1/heartbeat/stop` (graceful stop) wired into `create_app(heartbeat=...)`. Used `on_event` decorators (not lifespan) to avoid modifying the existing `FastAPI()` call.
- ✅ 41C: `tests/test_heartbeat.py` — 20 unit tests using pytest-asyncio (auto mode): config defaults/keys/storage, init/status, start/stop, double-start no-op, max_ticks=1/3/5 exact stops, control_plane.tick() called per loop, no-CP no-error, exception-swallowing, status reflects state, tick_count persists across stop.
- ✅ 41D: `tests/test_heartbeat_web.py` — 10 FastAPI TestClient tests: status 200/no-hb defaults/required keys/zero before run/interval matches/custom interval, stop 200/no-hb stopped=False/with-hb stopped=True, end-to-end heartbeat-drives-control-plane via asyncio.run.
- ✅ 41E: `scripts/prove.py` — 99 test modules registered.
- ✅ 41F: README Phase Map updated; Phase 42 planned.

**Phase 42 — Complete.** All 102 test modules green. Two-part phase: (A) `on_event` → `lifespan` migration eliminates the 36 FastAPI deprecation warnings from Phase 41; (B) `pradyos/cli.py` — stdlib-only HTTP client for a running PradyOS instance:

- ✅ 42A: `pradyos/sovereign_web.py` patched — added `from contextlib import asynccontextmanager`, injected `_lifespan` context manager inside `create_app()` (start heartbeat on enter, stop on exit), changed `FastAPI(...)` call to include `lifespan=_lifespan`, deleted both `@app.on_event` blocks. Verified: `grep on_event` → empty; Phase 41 heartbeat web tests pass with `-W error::DeprecationWarning` (zero warnings).
- ✅ 42B: `pradyos/cli.py` — `argparse` + `urllib.request` only; commands: `status` (GET /api/v1/os/control + table), `tick`, `signals`, `signal <name> [--limit N]`, `memory get/set [--namespace] [--ttl]`, `heartbeat`, `health`; `--url` flag (default http://localhost:8000); 5s timeout; clean error messages on HTTP/connection failure; all command logic in `run_*()` functions, importable; `_http_get`/`_http_post`/`_table` helpers; entry via `python -m pradyos.cli`.
- ✅ 42C: `tests/test_cli.py` — 20 unit tests using `unittest.mock.patch` on `urllib.request.urlopen` (CM-style mock); covers status/tick/signals/signal_detail/memory get-set/heartbeat/health + `_http_get`/`_http_post` request shape and Content-Type header.
- ✅ 42D: `tests/test_lifespan_web.py` — 10 FastAPI TestClient tests using context-manager pattern to fire lifespan: app starts without DeprecationWarning, heartbeat auto-start/stop, no-heartbeat clean start, status endpoint reflects running=True, POST /stop during lifespan, max_ticks advances, no on_event warning on `create_app()`, param wiring.
- ✅ 42E: `scripts/prove.py` — 102 test modules registered.
- ✅ 42F: README Phase Map updated; Phase 43 planned.

**Phase 43 — Complete.** All 104 test modules green. **The most important phase.** Without this, the OS cannot safely act autonomously. `GuardrailGate` classifies every intended action by risk (SAFE/LOW/MEDIUM/HIGH/CRITICAL); SAFE/LOW are auto-approved with journal trail; MEDIUM/HIGH/CRITICAL are queued in `ApprovalQueue` for explicit user approval; CRITICAL requires a `reason`. The queue supports approve/reject/expire-stale with TTL fallback. Stdlib only, thread-safe:

- ✅ 43A: `pradyos/core/guardrail.py` — `RiskLevel` enum, `ActionRequest` dataclass (uuid id + to_dict), `GuardrailGate.submit()` (raises ValueError on CRITICAL+no-reason, auto-approves SAFE/LOW with journal record, queues MEDIUM/HIGH/CRITICAL), `status()` (auto_approve_levels + pending queue_size).
- ✅ 43B: `pradyos/core/approval_queue.py` — `ApprovalStatus` enum (PENDING/APPROVED/REJECTED/EXPIRED), `ApprovalEntry` dataclass, `ApprovalQueue` with `add()` (creates PENDING from request), `approve()`/`reject()` (sets resolved_at + resolver_note), `expire_stale()` (TTL sweep), `get()`, `list_by_status()` (sorted by requested_at), `count()` (by status string/enum/None); thread-safe via `threading.Lock`.
- ✅ 43C: `pradyos/sovereign_web.py` patched — `GET /api/v1/guardrail/status`, `POST /api/v1/guardrail/submit`, `GET /api/v1/approvals?status=X`, `POST /api/v1/approvals/{id}/approve`, `POST /api/v1/approvals/{id}/reject`, `POST /api/v1/approvals/expire` wired into `create_app(guardrail_gate=..., approval_queue=...)`.
- ✅ 43D: `tests/test_guardrail.py` — 20 unit tests covering ActionRequest fields/serialization, RiskLevel enum, gate init/submit-safe/submit-low/submit-medium-queues/submit-high-queues, CRITICAL-no-reason raises, CRITICAL-with-reason queues, journal integration (auto vs pending), status keys, queue add/approve/reject/expire/count.
- ✅ 43E: `tests/test_approval_web.py` — 10 FastAPI tests (guardrail status no-gate/with-gate, submit safe/medium/invalid-risk, approvals list, approve/reject endpoints, expire count, full submit-HIGH→approve→list-shows-approved flow).
- ✅ 43F: `scripts/prove.py` — 104 test modules registered.
- ✅ 43G: README Phase Map updated; Phase 44 planned.

**Phase 44 — Complete.** All 106 test modules green. Sovereign ExecutionEngine — the bridge between "OS decided" and "OS acted". Enforces two hard rules: (1) `entry.status == APPROVED` (PENDING→BLOCKED, REJECTED→REJECTED, EXPIRED→EXPIRED); (2) base command must be on the explicit allowlist (empty allowlist = locked engine). Every run recorded to DecisionJournal:

- ✅ 44A: `pradyos/core/execution_engine.py` — `ExecutionStatus` enum (SUCCESS/FAILED/BLOCKED/REJECTED/EXPIRED), `ExecutionResult` dataclass with `to_dict()`, `ExecutionEngine` with `run(entry, timeout=None)` (status+allowlist gates, `subprocess.run` with capture+text+timeout, blocked/rejected/expired do NOT append to history), `history(limit)`, `status()` (allowlist + total_runs + last_status); thread-safe via `threading.Lock`.
- ✅ 44B: `pradyos/sovereign_web.py` patched — `GET /api/v1/execute/status`, `GET /api/v1/execute/history?limit=N`, `POST /api/v1/execute/{entry_id}` (looks up via `approval_queue.get`, 404 if missing, 400 if no engine) wired into `create_app(execution_engine=...)`.
- ✅ 44C: `tests/test_execution_engine.py` — 20 unit tests; uses `sys.executable -c "<code>"` instead of `echo` for cross-platform safety (Windows has no `echo` binary). Covers init/status, PENDING→BLOCKED, REJECTED, EXPIRED, not-in-allowlist BLOCKED, empty allowlist locks, SUCCESS with stdout/returncode/duration, history append, FAILED nonzero exit, journal recording, BLOCKED-no-history, history limit/empty, thread safety with 10 concurrent runs, last_status tracking.
- ✅ 44D: `tests/test_execution_web.py` — 10 FastAPI TestClient tests covering all 3 endpoints, no-engine fallbacks, unknown-entry 404, PENDING→blocked, APPROVED+allowlist→success, history reflects runs.
- ✅ 44E: `scripts/prove.py` — 106 test modules registered.
- ✅ 44F: README Phase Map updated; Phase 45 planned.

**Phase 45 — Complete.** All 108 test modules green. Sovereign ReasoningEngine — forward-chaining planner; given a goal string and a state snapshot, matches rules by trigger substring (case-insensitive), orders steps so satisfied-precondition steps fire first, and computes confidence as the fraction of all precondition pairs across all steps satisfied by the state. Stdlib only, no LLM calls:

- ✅ 45A: `pradyos/core/reasoning_engine.py` — `ReasoningStep` + `ReasoningPlan` dataclasses with `to_dict()`; `ReasoningEngine` with `add_rule()` (validates required keys: trigger/action/risk_level/rationale/preconditions), `rule_count()`, `plan(goal, state)` (substring trigger match → ordered steps → confidence rounded to 4dp; vacuous 1.0 when no steps or no preconditions), `status()` (rule_count + auto_approve_levels); thread-safe via `threading.Lock`.
- ✅ 45B: `pradyos/sovereign_web.py` patched — `GET /api/v1/reason/status`, `POST /api/v1/reason/rules` (400 on missing keys), `POST /api/v1/reason` (400 on missing goal) wired into `create_app(reasoning_engine=...)`.
- ✅ 45C: `tests/test_reasoning_engine.py` — 20 unit tests (init/rule_count, add_rule increments/validates, plan empty/match/no-match, step fields, ordering satisfied-first, confidence 1.0/partial 0.5/zero, state_used echo, created_at recent, status keys, 20 concurrent add_rule).
- ✅ 45D: `tests/test_reasoning_web.py` — 10 FastAPI TestClient tests covering all 3 endpoints, no-engine 400, missing-key 400, response shape, full add-rule → reason flow.
- ✅ 45E: `scripts/prove.py` — 108 test modules registered.
- ✅ 45F: README Phase Map updated; Phase 46 planned.

**Phase 46 — Complete.** All 110 test modules green. Sovereign WebAgent — stdlib-only HTTP research agent (urllib + html.parser, no requests/httpx); guardrail-gated fetches with SnapshotStore-backed caching and HTML link extraction for search:

- ✅ 46A: `pradyos/core/web_agent.py` — `WebResult` dataclass with `to_dict()`; `WebAgent` with `fetch(url)` (cache check → guardrail check → urlopen → cache save), `search(query, engine_url, max_results)` (guardrail check → fetch DDG HTML → `_LinkParser` extracts hrefs → fetch each link, excluding engine domain), `status()` (cache/guardrail flags + max_age + timeout); thread-safe via `threading.Lock`; duck-typed guardrail: prefers `gate.evaluate()` (mock-friendly), falls back to Phase 43 `gate.submit()` with AUTO_APPROVE_LEVELS check; DDG `/l/?uddg=` redirect URLs are unwrapped via `_extract_absolute_url`.
- ✅ 46B: `pradyos/sovereign_web.py` patched — `GET /api/v1/web/status`, `GET /api/v1/web/fetch?url=X`, `POST /api/v1/web/search` (400 on missing query / no agent) wired into `create_app(web_agent=...)`.
- ✅ 46C: `tests/test_web_agent.py` — 20 unit tests; ZERO real HTTP — all `urllib.request.urlopen` mocked via `unittest.mock.patch`. Covers WebResult fields, init, fetch success/failure/cache-hit/cache-miss/cache-save, guardrail block + approve, search list/blocked/fetch-fail, HTML link parsing, max_results, engine-domain exclusion, status keys/cache_enabled/guardrail_enabled.
- ✅ 46D: `tests/test_web_agent_web.py` — 10 FastAPI TestClient tests using a `_StubAgent`: status 200/keys/defaults, fetch 422-no-url / 400-no-agent / WebResult fields, search 400-no-agent / 400-no-query / results key / results is list.
- ✅ 46E: `scripts/prove.py` — 110 test modules registered.
- ✅ 46F: README Phase Map updated; Phase 47 planned.

**Phase 47 — Complete.** All 112 test modules green. Sovereign MemoryGraph — lightweight in-memory directed graph with `GraphNode`/`GraphEdge` dataclasses, BFS pathfinding, optional SnapshotStore persistence; stdlib only:

- ✅ 47A: `pradyos/core/memory_graph.py` — `GraphNode` + `GraphEdge` dataclasses with `to_dict()`; `MemoryGraph` with `add_node()` (idempotent — same name updates metadata, no duplicate), `add_edge()` (auto-creates missing src/dst, dedups by (src,dst,relation) and updates weight), `get_node()`, `get_neighbors(name, relation=None)`, `shortest_path()` via BFS (`[src]` if src==dst, `None` if unreachable or unknown), `node_count()`/`edge_count()`, `_save()`/`_load()` for SnapshotStore persistence (namespace='memory_graph', key='graph_state'); thread-safe via `threading.Lock` with internal `_save_locked()` to avoid re-acquiring while inside `add_edge`.
- ✅ 47B: `pradyos/sovereign_web.py` patched — `GET/POST /api/v1/memgraph/nodes`, `POST /api/v1/memgraph/edges`, `GET /api/v1/memgraph/neighbors/{name}?relation=X`, `GET /api/v1/memgraph/path?src=X&dst=Y` wired into `create_app(memory_graph=...)`. **Deviation:** Phase 17 already owns `/api/v1/graph/*` with a completely different `MemoryGraph` (uses `kind`/`label`/`attributes`); Phase 47 uses `/api/v1/memgraph/*` to coexist without breaking Phase 17 tests. Import aliased as `Phase47MemoryGraph` to avoid symbol clash.
- ✅ 47C: `tests/test_memory_graph.py` — 20 unit tests (init, add_node returns/count/duplicate-updates-metadata, add_edge returns/count/auto-create-src/auto-create-dst/duplicate-updates-weight, get_node correct/unknown, get_neighbors connected/relation-filter/unknown, shortest_path src==dst/chain/no-path/unknown-src, persistence via real SnapshotStore in tmp_path, 30 concurrent add_node).
- ✅ 47D: `tests/test_memory_graph_web.py` — 10 FastAPI TestClient tests covering all 5 endpoints, no-graph fallbacks, 400 on missing required keys, and full add-nodes→add-edge→shortest-path flow.
- ✅ 47E: `scripts/prove.py` — 112 test modules registered.
- ✅ 47F: README Phase Map updated; Phase 48 planned.

**Phase 48 — Complete.** All 114 test modules green. Sovereign EventSourcing — append-only per-stream event log with auto-incrementing sequences, declarative reducers, and snapshot-backed persistence; stdlib only:

- ✅ 48A: `pradyos/core/event_store.py` — `Event` dataclass with `to_dict()`; `EventStore` with `append(stream, event_type, payload)` (uuid4 id, sequence=len+1 atomically under lock — no duplicates under concurrency), `read(stream, from_seq=0)` (sequence > from_seq), `project(stream, reducer, initial=None)` (fold under lock-released list copy so reducer can be slow), `stream_names()`, `event_count(stream=None)`, `_save_locked()` per-stream (namespace='event_store', key=stream), `_load()` restores all streams on init via `list_keys`; thread-safe via `threading.Lock`.
- ✅ 48B: `pradyos/sovereign_web.py` patched — `POST /api/v1/events/{stream}` (400 on missing event_type / no store), `GET /api/v1/events/{stream}?from_seq=N`, `POST /api/v1/events/{stream}/project` (declarative reducer: for each event, find first matching `match_type` step, merge its `updates` into state) wired into `create_app(event_store=...)`. The `/project` route is registered BEFORE `/{stream}` POST so the literal `project` segment doesn't get captured as the stream name.
- ✅ 48C: `tests/test_event_store.py` — 20 unit tests (init, append returns/sequence-1/sequence-2/uuid-hex/recent-occurred_at, read all/from_seq=1/unknown, project unknown→initial/folds/empty→initial, stream_names sorted/empty, event_count total/scoped, Event.to_dict keys, persistence reload-events/sequence-preserved-and-continues, thread safety 40 concurrent appends with no duplicate sequences).
- ✅ 48D: `tests/test_event_sourcing_web.py` — 10 FastAPI TestClient tests (POST fields/missing-type-400/no-store-400, GET events+count/from_seq=0/no-store-empty, project state-key/missing-reducer_steps-400, full append-2-then-project flow, match_type merge correctness).
- ✅ 48E: `scripts/prove.py` — 114 test modules registered.
- ✅ 48F: README Phase Map updated; Phase 49 planned.

**Phase 49 — Complete.** All 116 test modules green. Sovereign TaskQueue + WorkerPool — priority work queue backed by `queue.PriorityQueue` with thread-pool execution; stdlib only (threading + queue + uuid):

- ✅ 49A: `pradyos/core/task_queue.py` — `Task` dataclass with `to_dict()`; `TaskQueue` with `submit(name, payload, priority=5)` (uuid4 id, monotonic FIFO tie-breaker so equal-priority tasks dequeue in submit order), `get()`, `list_tasks(status=None)` (sorted by created_at), `cancel()` (pending only → status='failed' error='cancelled'), `_mark_running/done/failed`; `WorkerPool` spawns N daemon threads that pull `(priority, seq, task_id)` tuples, swallow ALL handler exceptions (pool never crashes), and exit cleanly when `stop()` injects `_STOP_SENTINEL` tuples; `is_alive()` reports thread liveness; thread-safe via `threading.Lock` for the task dict (PriorityQueue handles its own locking).
- ✅ 49B: `pradyos/sovereign_web.py` patched — `POST /api/v1/tasks` (400 on missing name / no queue), `GET /api/v1/tasks?status=X`, `GET /api/v1/tasks/{id}` (404 if missing), `DELETE /api/v1/tasks/{id}` (cancel pending, 404 otherwise) wired into `create_app(task_queue=...)`.
- ✅ 49C: `tests/test_task_queue.py` — 20 unit tests (init, submit returns/uuid/storage, get unknown, list sorted/filter-pending/filter-done, cancel pending/non-pending/unknown, _mark_running/done/failed, to_dict keys, WorkerPool executes/marks-failed-on-exception/clean shutdown, 50 concurrent submits, 3-worker pool processes 10 tasks). Uses a `_wait_until` polling helper for async worker tests.
- ✅ 49D: `tests/test_task_queue_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-queue fallbacks, 400/404 handling, status filter, end-to-end submit→cancel flow.
- ✅ 49E: `scripts/prove.py` — 116 test modules registered.
- ✅ 49F: README Phase Map updated; Phase 50 planned.

**Phase 50 — Complete.** All 118 test modules green. Sovereign PubSub — in-process publish/subscribe message broker; topics auto-created on subscribe/publish; callbacks fire synchronously in publishing thread; broker is uncrashable because publish() swallows all callback exceptions; stdlib only:

- ✅ 50A: `pradyos/core/pubsub.py` — `Topic` + `Subscription` dataclasses (`Subscription.to_dict()` omits the non-serializable `callback`); `PubSubBroker` with `subscribe()` (auto-creates topic, uuid4 sub id), `unsubscribe()` (topic persists even at 0 subs), `publish()` (snapshots callbacks under lock then calls OUTSIDE lock to avoid deadlock on re-entrant subscribe; returns count of SUCCESSFUL callbacks only), `list_topics()` (sorted, with subscriber_count + created_at), `list_subscriptions(topic=None)`, `count_subscribers()`; thread-safe via `threading.Lock`.
- ✅ 50B: `pradyos/sovereign_web.py` patched — `GET /api/v1/pubsub/topics` (registered FIRST so literal `topics` doesn't get captured as `{topic}` param), `GET /api/v1/pubsub/{topic}/subscribers`, `POST /api/v1/pubsub/{topic}` (400 on missing message / no broker; coerces non-dict messages to `{"value": ...}`) wired into `create_app(pubsub=...)`.
- ✅ 50C: `tests/test_pubsub.py` — 20 unit tests (init, subscribe returns/auto-creates-topic/uuid/unique-ids, unsubscribe true/false/removes, publish callback-invocation/success-count/swallows-exceptions/zero-subs/auto-creates, list_topics sorted/keys/decrements, list_subscriptions all/filtered, count_subscribers, 50 concurrent subscribes).
- ✅ 50D: `tests/test_pubsub_web.py` — 10 FastAPI TestClient tests covering all 3 endpoints, no-broker fallbacks, subscribe-then-publish end-to-end, topic-list growth, subscriber count increment.
- ✅ 50E: `scripts/prove.py` — 118 test modules registered.
- ✅ 50F: README Phase Map updated; Phase 51 planned.

**Phase 51 — Complete.** All 120 test modules green. Sovereign StateSync — bidirectional message mirror between two named PubSubBrokers; per-topic closures preserve topic identity through forwarding; `__synced__` sentinel key on each forwarded message prevents infinite loops even when both peers point at the same broker; stdlib only:

- ✅ 51A: `pradyos/core/statesync.py` — `SyncPeer` + `SyncSession` dataclasses with `to_dict()` (Peer omits `subscription_ids`); `StateSyncManager` with `register_broker(name, broker)` (overwrite silently), `create_session(broker_a_name, broker_b_name, topics_a, topics_b)` (validates broker names → ValueError, builds per-topic closure-based forwarders that subscribe on source and republish on target with `{__synced__: True}` sentinel; `synced_count` tracks successful forwards), `stop_session()` (unsubscribes all peers, sets `active=False`), `get_session()`, `list_sessions(active_only=False)` (sorted by created_at), `count()`; thread-safe via `threading.Lock` on the manager state.
- ✅ 51B: `pradyos/sovereign_web.py` patched — `GET /api/v1/statesync/sessions?active_only=true`, `POST /api/v1/statesync/sessions` (400 on missing keys / unknown broker), `DELETE /api/v1/statesync/sessions/{id}` (404 if missing) wired into `create_app(statesync=...)`.
- ✅ 51C: `tests/test_statesync.py` — 20 unit tests (init, register-overwrite, create-validation ValueError on each missing broker, returns SyncSession + active + uuid, A→B sync, B→A sync, cycle detection (one publish → exactly 1 forward), synced_count increments, stop_session true/false/unsubscribes-so-no-more-forwards, list sorted/active_only, get correct/unknown, count includes stopped).
- ✅ 51D: `tests/test_statesync_web.py` — 10 FastAPI TestClient tests covering all 3 endpoints, no-manager fallbacks, missing-keys-400, unknown-broker-400, full POST→GET→DELETE→GET-active-only flow.
- ✅ 51E: `scripts/prove.py` — 120 test modules registered.
- ✅ 51F: README Phase Map updated; Phase 52 planned.

**Phase 52 — Complete.** All 122 test modules green. Sovereign DistributedLock — TTL-based named mutex; crashed holders cannot deadlock the system because every lock expires automatically; same-holder re-acquire refreshes TTL by design; stdlib only:

- ✅ 52A: `pradyos/core/distributed_lock.py` — `DistributedLock` dataclass with `is_expired()` and `to_dict()`; `LockManager` with `acquire(name, holder_id, ttl=30)` (returns None if held by another non-expired holder; same holder re-acquires by replacing; expired locks can be taken by anyone), `release(name, holder_id)` (True only if caller is non-expired current holder), `refresh()` (extend TTL when caller is current holder and not expired), `is_locked()` (only True if held and not expired), `list_locks()` (excludes expired but doesn't remove them, sorted by acquired_at), `expire_stale()` (removes expired, returns count), `count(include_expired=False)`; thread-safe via `threading.Lock`.
- ✅ 52B: `pradyos/sovereign_web.py` patched — `GET /api/v1/locks`, `POST /api/v1/locks` (400 on missing keys, 409 when already held), `POST /api/v1/locks/{name}/refresh` (registered BEFORE delete so the literal `/refresh` doesn't get consumed), `DELETE /api/v1/locks/{name}?holder_id=...` wired into `create_app(lock_manager=...)`.
- ✅ 52C: `tests/test_distributed_lock.py` — 20 unit tests (init, acquire fields/is_locked/second-caller-None/same-holder-replaces/expired-can-be-taken, release true/wrong-holder/unknown, refresh true/wrong-holder/expired, is_locked unknown/after-release, list excludes-expired/sorted, expire_stale removes-and-counts, count excludes/includes-expired).
- ✅ 52D: `tests/test_distributed_lock_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-manager fallbacks, 400/404/409 status codes, end-to-end acquire→refresh→release.
- ✅ 52E: `scripts/prove.py` — 122 test modules registered.
- ✅ 52F: README Phase Map updated; Phase 53 planned.

**Phase 53 — Complete.** All 124 test modules green. Sovereign CircuitBreaker — per-service failure tracker with CLOSED → OPEN → HALF_OPEN → CLOSED/OPEN state machine; OPEN refuses calls immediately, recovery_timeout transitions to HALF_OPEN, success returns to CLOSED, failure flips back to OPEN; stdlib only:

- ✅ 53A: `pradyos/core/circuit_breaker.py` — `CircuitOpenError`, `BreakerState` dataclass with `to_dict()` (omits internal `half_open_probes` counter), `CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, half_open_max=1)` with `call(name, fn, *args, **kwargs)` (auto-creates state on first use; OPEN check at entry → maybe transition to HALF_OPEN or raise; fn executes OUTSIDE lock so slow handlers don't block other callers; success in CLOSED resets failure_count; success in HALF_OPEN → CLOSED; failure in CLOSED checks threshold → OPEN; failure in HALF_OPEN increments probe count → OPEN at half_open_max), `get_state()`, `reset()` (zeros out all state), `list_breakers()` (sorted by name), `count()`; thread-safe via `threading.Lock`.
- ✅ 53B: `pradyos/sovereign_web.py` patched — `GET /api/v1/breakers`, `POST /api/v1/breakers` (registers a named breaker via `_get_or_create_locked`), `POST /api/v1/breakers/{name}/reset` (registered BEFORE bare `/{name}` GET so the literal `/reset` doesn't get captured), `GET /api/v1/breakers/{name}` (404 if missing) wired into `create_app(circuit_breaker=...)`.
- ✅ 53C: `tests/test_circuit_breaker.py` — 20 unit tests covering init, call-success-creates-CLOSED, closed-success-resets-count, closed-failure-increments, CLOSED→OPEN at threshold, OPEN raises CircuitOpenError without invoking fn, OPEN→HALF_OPEN after recovery_timeout with success-to-CLOSED, HALF_OPEN failure → OPEN with opened_at reset, half_open_max=2 requires two probe failures, get_state, reset, list_breakers sorted/fields, count, 50 concurrent calls thread safety.
- ✅ 53D: `tests/test_circuit_breaker_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-cb fallbacks, 400/404 status codes, end-to-end register→reset→count flow.
- ✅ 53E: `scripts/prove.py` — 124 test modules registered.
- ✅ 53F: README Phase Map updated; Phase 54 planned.

**Phase 54 — Complete.** All 126 test modules green. Sovereign RetryPolicy — configurable retry executor with exponential back-off, uniform jitter, and per-exception filtering via `retry_on`. The last attempt of an exhausted retry is marked `outcome="exhausted"`; non-retryable exceptions short-circuit immediately. Stdlib only:

- ✅ 54A: `pradyos/core/retry_policy.py` — `AttemptRecord` dataclass with `to_dict()`; `RetryPolicy(max_attempts=3, base_delay=1.0, backoff_factor=2.0, jitter=0.1, retry_on=(Exception,))` with `execute(name, fn, *args, **kwargs)` (1-indexed attempts; success records `outcome="success"`; failure records `outcome="failure"` and either retries with `base_delay * factor^(attempt-1) + uniform(-jitter, jitter)` clamped ≥0, or — if exhausted — flips last record to `"exhausted"` and re-raises; non-retry_on exceptions re-raise immediately after recording), `get_history()`, `clear_history()`, `list_names()` (sorted), `count(name=None)`; thread-safe via `threading.Lock`.
- ✅ 54B: `pradyos/sovereign_web.py` patched — `GET /api/v1/retry` (names + count), `POST /api/v1/retry/execute` (built-in test fn with `should_fail`/`fail_attempts` knobs; catches exhausted exceptions and returns them in the response rather than HTTP 500), `GET /api/v1/retry/{name}/history`, `DELETE /api/v1/retry/{name}/history` (404 if missing) wired into `create_app(retry_policy=...)`.
- ✅ 54C: `tests/test_retry_policy.py` — 20 unit tests (init, success first-attempt/after-2-failures/records-outcome, exhausted raises-original/last-record-exhausted, non-retry_on reraises-immediately/records-failure, sleep never negative under high jitter, get/clear_history, list_names sorted/empty, count total/scoped, AttemptRecord fields, elapsed is positive float, 20 concurrent execute calls thread safety).
- ✅ 54D: `tests/test_retry_policy_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-policy fallbacks, success/retry-once-succeed/exhausted scenarios, history GET/DELETE, 404 on unknown name.
- ✅ 54E: `scripts/prove.py` — 126 test modules registered.
- ✅ 54F: README Phase Map updated; Phase 55 planned.

**Phase 55 — Complete.** All 128 test modules green. Sovereign BulkheadPool — fixed-capacity thread-pool isolation per named service; `submit` raises `BulkheadRejectedError` immediately when `in_flight >= max_workers + queue_depth`, never blocks; per-pool counters (submitted/completed/rejected/active) update under lock; stdlib + `concurrent.futures` only:

- ✅ 55A: `pradyos/core/bulkhead_pool.py` — `BulkheadRejectedError(RuntimeError)`, `PoolStats` dataclass with `to_dict()`; `BulkheadPool(max_workers=4, queue_depth=8, name="default")` tracks `_in_flight` under lock; `submit()` (capacity check → reject-with-counter or accept-and-submit; `add_done_callback` decrements in_flight + increments completed), `get_stats()` (computes `active = min(in_flight, max_workers)`), `reset_stats()` (zeros submitted/completed/rejected but preserves in_flight for running tasks), `shutdown(wait=True)`; `BulkheadManager` with `create()` (ValueError on duplicate), `get()`, `delete()` (shuts down pool then removes), `list_pools()` (sorted), `count()`; thread-safe via `threading.Lock`.
- ✅ 55B: `pradyos/sovereign_web.py` patched — `GET /api/v1/bulkheads`, `POST /api/v1/bulkheads` (400 on missing name; "pool already exists" on duplicate), `POST /api/v1/bulkheads/{name}/submit` (registered BEFORE bare `/{name}` GET to avoid path-param capture; submits a `time.sleep(sleep)` no-op; **HTTP 429** with `submitted: False` on `BulkheadRejectedError`), `GET /api/v1/bulkheads/{name}` (404 if missing) wired into `create_app(bulkhead_manager=...)`.
- ✅ 55C: `tests/test_bulkhead_pool.py` — 20 unit tests (init fields, submit returns Future, submitted/completed counters, rejected counter at-capacity, BulkheadRejectedError raised, reset_stats zeros, get_stats type, PoolStats fields, shutdown, manager create/get/get-unknown/duplicate-ValueError/delete-true/delete-unknown/list-sorted/count, 30 concurrent submits to large pool all succeed, 5 concurrent submits to capacity-1 pool → at least 1 rejected with gate-based slow task).
- ✅ 55D: `tests/test_bulkhead_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints; the capacity-1 test uses a 1.0s sleep on the first submit to deterministically force the second submit into the rejected/429 path.
- ✅ 55E: `scripts/prove.py` — 128 test modules registered.
- ✅ 55F: README Phase Map updated; Phase 56 planned.

**Phase 56 — Complete.** All 130 test modules green. Sovereign TimeoutGuard — per-call wall-clock deadline enforcement. Each `execute()` spawns a fresh single-worker `ThreadPoolExecutor` (no shared state between callers), waits with `future.result(timeout=…)`, records the outcome (success/timeout/error) in a per-name history, and raises `TimeoutExpiredError` (subclass of `RuntimeError`) on deadline overrun. Stdlib + `concurrent.futures` only:

- ✅ 56A: `pradyos/core/timeout_guard.py` — `GuardRecord` dataclass with `to_dict()`; `TimeoutExpiredError`; `TimeoutGuard(default_timeout=5.0)` with `execute(name, fn, *args, timeout=None, **kwargs)` (per-call timeout override, fresh executor per call, `shutdown(wait=False)` lets a timed-out task finish in background, records always written), `get_history()`, `clear_history()`, `list_names()` (sorted), `count(name=None)`; thread-safe via `threading.Lock`.
- ✅ 56B: `pradyos/sovereign_web.py` patched — `GET /api/v1/timeouts` (names + total), `POST /api/v1/timeouts/execute` (built-in `_no_op` with `sleep`/`timeout`/`should_error` knobs; **HTTP 408** on timeout, **HTTP 500** on fn error), `GET /api/v1/timeouts/{name}/history`, `DELETE /api/v1/timeouts/{name}/history` (404 if missing) wired into `create_app(timeout_guard=...)`. The literal `/execute` POST is registered BEFORE the `/{name}/history` routes so `execute` isn't captured as a name.
- ✅ 56C: `tests/test_timeout_guard.py` — 20 unit tests (init/default_timeout, success returns/records-outcome/elapsed≥0, timeout raises/records-outcome, error reraises/records-outcome/records-message, get/clear_history, get_history unknown/order, list_names sorted, count scoped/total, per-call timeout override, TimeoutExpiredError subclass of RuntimeError, 20 concurrent execute).
- ✅ 56D: `tests/test_timeout_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-guard fallback, success outcome, **408** on `sleep=1.0` + `timeout=0.05`, **500** on `should_error=true`, history GET/DELETE.
- ✅ 56E: `scripts/prove.py` — 130 test modules registered.
- ✅ 56F: README Phase Map updated; Phase 57 planned.

**Phase 57 — Complete.** All 132 test modules green. Sovereign SemaphoreGate — named counting semaphores with per-name capacity; wraps `threading.Semaphore` with live counters (acquired_total / released_total / timeout_total / available). Idempotent `create()` for same-capacity, ValueError for capacity mismatch (web layer → HTTP 409). Stdlib only:

- ✅ 57A: `pradyos/core/semaphore_gate.py` — `SemaphoreStats` dataclass with `to_dict()`; `SemaphoreTimeoutError(RuntimeError)` exported for downstream code that prefers exception-style signaling; `SemaphoreNotFoundError(KeyError)`; `_Entry` slot-class bundles the semaphore + counters; `SemaphoreGate` with `create(name, capacity=1)` (idempotent same-capacity, ValueError on mismatch), `acquire(name, timeout=None)` (releases the gate lock before blocking on the semaphore so other gate ops don't stall; returns True/False; increments correct counter), `release(name)`, `get_stats()` (reads `semaphore._value` under lock for `available`), `list_names()` (sorted), `delete()`; thread-safe via `threading.Lock`.
- ✅ 57B: `pradyos/sovereign_web.py` patched — `GET /api/v1/semaphores`, `POST /api/v1/semaphores` (400 missing name; 409 on capacity mismatch), `POST /api/v1/semaphores/{name}/acquire` (defaults timeout=5.0 for HTTP safety), `POST /api/v1/semaphores/{name}/release`, `GET /api/v1/semaphores/{name}` wired into `create_app(semaphore_gate=...)`. Literal `/acquire` and `/release` suffixes registered BEFORE the bare `/{name}` GET to prevent path-param capture.
- ✅ 57C: `tests/test_semaphore_gate.py` — 20 unit tests (init, create returns/idempotent/mismatch-ValueError, acquire true/increments/timeout-zero-false-when-full/increments-timeout, release increments/restores-slot, get_stats type/available/unknown-NotFound, unknown acquire/release-NotFound, list sorted, delete true/false, SemaphoreTimeoutError type, 10 threads acquire+release on capacity=5 fully back to 5 available).
- ✅ 57D: `tests/test_semaphore_web.py` — 10 FastAPI TestClient tests covering all 5 endpoints, no-gate fallbacks, idempotent create, 409 on capacity mismatch, acquire/release end-to-end, acquire-on-full returns acquired=False.
- ✅ 57E: `scripts/prove.py` — 132 test modules registered.
- ✅ 57F: README Phase Map updated; Phase 58 planned.

**Phase 58 — Complete.** All 134 test modules green. Sovereign EventFilter — declarative, composable filter pipeline over event dicts; 10 operators (eq/neq/gt/lt/gte/lte/contains/startswith/endswith/regex); dot-notation field paths with safe missing-key handling; AND/OR compounds; named filter registry. Stdlib only:

- ✅ 58A: `pradyos/core/event_filter.py` — `FilterRule(field, op, value)` with `matches(event)` (`_resolve` walks dot-notation paths returning a `_MISSING` sentinel rather than raising; numeric comparison when both sides numeric, string comparison otherwise; regex compile errors return False; unknown op returns False); `EventFilter(rules, mode='AND')` (validates mode → ValueError, empty rules passes all); `EventFilterRegistry` with `register()` (overwrite ok), `get()`, `delete()`, `list_names()` (sorted), `apply(name, events)` (KeyError on unknown name → web layer translates to 404); thread-safe via `threading.Lock`.
- ✅ 58B: `pradyos/sovereign_web.py` patched — `GET /api/v1/filters`, `POST /api/v1/filters` (400 on missing name or invalid mode), `POST /api/v1/filters/{name}/apply` (404 on unknown name), `DELETE /api/v1/filters/{name}` wired into `create_app(event_filter_registry=...)`. The literal `/apply` POST is registered BEFORE the DELETE `/{name}` so it isn't captured as the name param.
- ✅ 58C: `tests/test_event_filter.py` — 20 unit tests (each of the 10 ops, missing-field-no-raise, dot-notation nested, unknown-op-false, EventFilter AND all-match/one-miss, OR one-match/all-miss, empty rules pass, invalid mode ValueError, registry register/get/apply/unknown-KeyError/delete-list).
- ✅ 58D: `tests/test_filter_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-registry fallbacks, 400 on invalid mode, 404 on unknown name, full create→apply→delete flow with zero/positive match counts.
- ✅ 58E: `scripts/prove.py` — 134 test modules registered.
- ✅ 58F: README Phase Map updated; Phase 59 planned.

**Phase 59 — Complete.** All 136 test modules green. Sovereign ThrottleMap — per-key sliding-window rate limiter using `time.monotonic()` (no wall-clock drift) and `collections.deque`. Distinct from Phase 23's global rate-limit shield: per-key independence, configurable limit+window per call, cumulative allowed/rejected counters. Stdlib only:

- ✅ 59A: `pradyos/core/throttle_map.py` — `ThrottleMap` with `allow(key, limit, window)` (purges timestamps older than `now - window` before checking; appends if `len < limit`, increments correct counter; auto-creates key on first call), `reset(key)` (clears deque + counters, True/False), `stats(key, limit, window)` (purges first, returns calls_in_window + allowed_total + rejected_total, None if unknown), `list_keys()` (sorted), `delete()`; thread-safe via `threading.Lock`.
- ✅ 59B: `pradyos/sovereign_web.py` patched — `GET /api/v1/throttle`, `POST /api/v1/throttle/check` (registered BEFORE `/{key}` so the literal `/check` isn't captured as a key; 400 on missing required fields), `GET /api/v1/throttle/{key}?limit=N&window=F` (400 on missing query params, 404 on unknown), `DELETE /api/v1/throttle/{key}` wired into `create_app(throttle_map=...)`.
- ✅ 59C: `tests/test_throttle_map.py` — 20 unit tests (init, allow under/over limit, window expiry resets, auto-create, reset true/false/restores capacity, stats None/calls/totals/zero-after-expiry, list sorted/includes, delete true/false/stats-none-after, independence between keys, **50 concurrent allows on limit=25 → exactly 25 allowed**, allowed+rejected sum = total calls).
- ✅ 59D: `tests/test_throttle_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-map fallbacks, 400 on missing fields, 404 on unknown key, end-to-end check→stats→delete flow.
- ✅ 59E: `scripts/prove.py` — 136 test modules registered.
- ✅ 59F: README Phase Map updated; Phase 60 planned.

**Phase 60 — Complete.** All 138 test modules green. Sovereign PipelineChain — composable named processing pipeline for event dicts. Each step is one of 5 built-in transforms (set/delete/rename field, uppercase/lowercase value); chains short-circuit on first `StepError`, never mutate the caller's input. Stdlib only:

- ✅ 60A: `pradyos/core/pipeline_chain.py` — `StepError(step_name, original_event, message)` exception; 5 pure transform functions (`set_field`/`delete_field`/`rename_field`/`uppercase_field`/`lowercase_field`) — uppercase/lowercase raise `StepError` directly on missing key or non-str value; `Step(name, transform_type, params)` and `PipelineChain(name, steps)` dataclasses; `PipelineChain.run()` shallow-copies the input then chains each transform's output to the next, re-wrapping any `StepError` with the step's user-given name and the ORIGINAL event for traceability; `PipelineRegistry` with `register`/`get`/`delete`/`list_chains` (sorted)/`run` (KeyError on unknown); thread-safe via `threading.Lock`.
- ✅ 60B: `pradyos/sovereign_web.py` patched — `GET /api/v1/pipelines`, `POST /api/v1/pipelines` (400 on missing name/steps), `POST /api/v1/pipelines/{name}/run` (404 on unknown chain, **422** on `StepError` with `step` key naming the failing step), `DELETE /api/v1/pipelines/{name}` wired into `create_app(pipeline_registry=...)`.
- ✅ 60C: `tests/test_pipeline_chain.py` — 20 unit tests (StepError fields, all 5 transforms incl. immutability, uppercase missing-key + lowercase non-str raise, chain single/multi-step/no-mutation/short-circuit/empty, registry init/register-get/overwrite/get-unknown/delete-true/delete-unknown/run-KeyError/StepError-propagation).
- ✅ 60D: `tests/test_pipeline_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-registry fallbacks, 400 on missing keys, 404 on unknown chain, 422 with step name on bad step, end-to-end register→run→delete flow.
- ✅ 60E: `scripts/prove.py` — 138 test modules registered.
- ✅ 60F: README Phase Map updated; Phase 61 planned.

**Phase 61 — Complete.** All 140 test modules green. Sovereign TagIndex — multi-value tag store; each tag is an inverted index into a set of item IDs; supports AND-intersection and OR-union searches across multiple tags; auto-cleans empty tag buckets so `list_tags()` never returns dead entries. Stdlib only:

- ✅ 61A: `pradyos/core/tag_index.py` — `TagIndex` with `tag(item_id, *tags)` (idempotent), `untag(item_id, *tags)` (drops empty buckets so they don't accumulate), `items(tag)` (sorted), `tags(item_id)` (reverse-lookup, sorted), `delete_item(item_id)` (removes from all tags + cleans empties, returns True iff found), `search(*tags, mode='all'|'any')` (intersection or union, empty tags → []), `list_tags()` (sorted by tag name with count), `count(tag=None)` (per-tag count or global unique-item count); thread-safe via `threading.Lock`.
- ✅ 61B: `pradyos/sovereign_web.py` patched — `GET /api/v1/tags`, `POST /api/v1/tags/tag` and `/untag`, `GET /api/v1/tags/items/{tag}`, `GET /api/v1/tags/search?tags=a,b&mode=all|any` (comma-split with whitespace strip + empty filter), `DELETE /api/v1/tags/items/{item_id}` (404 if item bore no tags) wired into `create_app(tag_index=...)`. Note: `GET /items/{tag}` and `DELETE /items/{item_id}` share the same path pattern but FastAPI dispatches on HTTP method — no conflict.
- ✅ 61C: `tests/test_tag_index.py` — 20 unit tests (init, tag adds + idempotent, items sorted/unknown, tags sorted/unknown, untag removes + no-op missing + cleans empty bucket, delete_item removes-all/unknown-false/cleans, search all/any/no-tags, list_tags counts + sorted, count by-tag + total-unique).
- ✅ 61D: `tests/test_tag_web.py` — 10 FastAPI TestClient tests covering all 6 endpoints, no-index fallbacks, full tag→search→delete flow with 404 on second delete.
- ✅ 61E: `scripts/prove.py` — 140 test modules registered.
- ✅ 61F: README Phase Map updated; Phase 62 planned.

**Phase 62 — Complete.** All 142 test modules green. Sovereign EventRouter — content-based routing for event dicts. Each route has a `name`, an AND-list of predicates (same shape as `EventFilter` conditions), and a `destination` string. `route(event)` returns the sorted list of destinations whose every predicate matches; falls back to `default_destination` (single-element list) when nothing matches. Stdlib only:

- ✅ 62A: `pradyos/core/event_router.py` — `Route` dataclass with `to_dict()` + `matches(event)` (empty predicate list matches anything; all predicates must match for a route to fire); 9 supported ops (eq/neq/gt/lt/gte/lte/contains/startswith/endswith); `_match_one` resolves field via `event.get(field, _MISSING)` and applies the op (missing field → only `neq` is True; numeric coerce to float for gt/lt/gte/lte with string fallback); `EventRouter(default_destination=None)` with `add_route()` (ValueError on duplicate name), `remove_route()`, `route(event)` (snapshots routes under lock, evaluates each, returns sorted destinations or `[default]`), `list_routes()`, `count()`; `RouterRegistry` with `create`/`get`/`delete`/`list_names`; thread-safe via `threading.Lock`.
- ✅ 62B: `pradyos/sovereign_web.py` patched — `GET /api/v1/routers`, `POST /api/v1/routers` (400 missing name; 409 duplicate; accepts initial `routes[]` array and `default_destination`), `POST /api/v1/routers/{name}/route` (returns `destinations` + `matched` count; 404 if router unknown — registered BEFORE bare `/{name}` DELETE so literal `/route` isn't captured), `DELETE /api/v1/routers/{name}` wired into `create_app(router_registry=...)`.
- ✅ 62C: `tests/test_event_router.py` — 21 unit tests (init, add_route returns/duplicate-ValueError/registration-order, remove_route true/unknown, route empty-preds-matches-all, each of 9 ops, missing-field eq-false + neq-true, compound predicates AND, multi-route fanout-sorted, default_destination applied/not-applied, registry create/get/delete/duplicate-ValueError).
- ✅ 62D: `tests/test_event_router_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-registry fallbacks, 400/409 status codes, end-to-end create→route→delete with default_destination behavior.
- ✅ 62E: `scripts/prove.py` — 142 test modules registered.
- ✅ 62F: README Phase Map updated; Phase 63 planned.

**Phase 63 — Complete.** All 144 test modules green. Sovereign AggregateRoot — domain-driven event-sourced aggregate primitive with monotonic version, in-memory event log, shallow-merge state projection, and replay-from-history support. Stdlib only:

- ✅ 63A: `pradyos/core/aggregate_root.py` — `DomainEvent` dataclass with `to_dict()`; `AggregateRoot(aggregate_id)` with `apply(event_type, payload)` (under lock: increment version, record event, shallow-merge into state), `get_state()` (returns copy), `get_events(since_version=0)` (filtered + sorted), `rebuild_state(events)` (full replay that resets state/version/log first then iterates in version order), `version` property, `event_count()`; `AggregateRegistry` with `get_or_create()` (idempotent), `get()`, `list_aggregates()` (sorted dicts with version/event_count/state_keys), `delete()`, `count()`; thread-safe via `threading.Lock` throughout.
- ✅ 63B: `pradyos/sovereign_web.py` patched — `GET /api/v1/aggregates`, `POST /api/v1/aggregates/{id}/events` (400 on missing event_type; auto-creates via `get_or_create`), `GET /api/v1/aggregates/{id}/state` (404 if missing), `GET /api/v1/aggregates/{id}/events?since_version=N` (404 if missing), `DELETE /api/v1/aggregates/{id}` wired into `create_app(aggregate_registry=...)`.
- ✅ 63C: `tests/test_aggregate_root.py` — 20 unit tests (init, apply returns/v1/v2/state-merge, get_state copy-isolation, get_events all/since/sorted, rebuild_state replay/version/count, registry get_or_create/idempotent/get-unknown/list-sorted/list-fields/delete-true/delete-unknown/count, 50 concurrent applies → no version duplicates or gaps).
- ✅ 63D: `tests/test_aggregate_web.py` — 10 FastAPI TestClient tests covering all 5 endpoints, no-registry fallbacks, 404 on unknown id, version=1 on first POST, since_version=1 skips earlier events.
- ✅ 63E: `scripts/prove.py` — 144 test modules registered.
- ✅ 63F: README Phase Map updated; Phase 64 planned.

**Phase 64 — Complete.** All 146 test modules green. Sovereign Command Bus — named handlers register at runtime, dispatch by name with a payload dict; each call produces a `CommandResult` recorded in a ring-buffer history (max 500). Stdlib only:

- ✅ 64A: `pradyos/core/command_bus.py` — `CommandResult` dataclass with `to_dict()`; `CommandBus(HISTORY_LIMIT=500)` with `register(name, handler)` (overwrites silently), `unregister()` (True/False), `dispatch(name, payload=None)` (unknown handler → success=False with diagnostic error; exception in handler → success=False/error=str(exc)/result={}; non-dict return wrapped as `{"value": ret}`; `duration_ms` measured via `time.perf_counter()`; ALWAYS appends to history), `history(limit=50)` (newest-first, capped at HISTORY_LIMIT), `list_handlers()` (sorted), `clear_history()` (returns count, empties deque); thread-safe via `threading.Lock`; `payload=None` defaults to `{}`.
- ✅ 64B: `pradyos/sovereign_web.py` directly edited (no patch script) — added `command_bus: Any | None = None` param and 4 endpoints: `GET /api/v1/commands/handlers`, `POST /api/v1/commands/dispatch` (400 on missing name), `GET /api/v1/commands/history?limit=N` (clamped 0–200), `DELETE /api/v1/commands/handlers/{name}` (404 if missing). **Procedural shift:** Phase 64 onward uses the Edit tool directly on `sovereign_web.py` — no more `scripts/patch_web_phaseN.py` files. The file was already valid Python through Phase 63's incremental edits; the patch scripts were just `string.replace()` wrappers around what Edit does natively.
- ✅ 64C: `tests/test_command_bus.py` — 20 unit tests (init, register/overwrite/unregister/list-sorted, dispatch unknown/known/result-passthrough/duration/dispatched_at-recent/exception-failure/history-append, history newest-first/limit/cap-at-500/clear-returns-count, ring-buffer 600→500, 50 concurrent dispatches, payload=None defaults to {}).
- ✅ 64D: `tests/test_command_web.py` — 10 FastAPI TestClient tests using a pre-registered `echo` handler; covers all 4 endpoints, no-bus fallbacks, 400 on missing name, 404 on unregister unknown.
- ✅ 64E: `scripts/prove.py` — 146 test modules registered.
- ✅ 64F: README Phase Map updated; Phase 65 planned.

**Phase 65 — Complete.** All 148 test modules green. Sovereign Query Bus — symmetric read-side mirror of the Command Bus. Same shape, swapped vocabulary (params/queried_at/query_name instead of payload/dispatched_at/command_name) so a single observability stack covers both write and read paths. Stdlib only:

- ✅ 65A: `pradyos/core/query_bus.py` — `QueryResult` dataclass with `to_dict()`; `QueryBus(HISTORY_LIMIT=500)` with `register(name, handler)` (overwrites silently), `unregister()` (True/False), `query(name, params=None)` (unknown handler → success=False with diagnostic error; exception → success=False/error=str(exc)/result={}; non-dict return wrapped as `{"value": ret}`; `duration_ms` via `time.perf_counter()`; ALWAYS appends to history), `history(limit=50)` (newest-first, capped at HISTORY_LIMIT), `list_handlers()` (sorted), `clear_history()` (returns count, empties deque); thread-safe via `threading.Lock`; `params=None` defaults to `{}`.
- ✅ 65B: `pradyos/sovereign_web.py` directly edited (no patch script) — added `query_bus: Any | None = None` param and 4 endpoints: `GET /api/v1/queries/handlers`, `POST /api/v1/queries/execute` (400 on missing name), `GET /api/v1/queries/history?limit=N` (clamped 0–200), `DELETE /api/v1/queries/handlers/{name}` (404 if missing).
- ✅ 65C: `tests/test_query_bus.py` — 20 unit tests (init, register/overwrite/unregister/list-sorted, query unknown/known/result-passthrough/duration/queried_at-recent/exception-failure/history-append, history newest-first/limit/cap-at-500/clear-returns-count, ring-buffer 600→500, 50 concurrent queries, params=None defaults to {}).
- ✅ 65D: `tests/test_query_web.py` — 10 FastAPI TestClient tests using a pre-registered `lookup` handler that returns `{"found": params.get("id")}`; covers all 4 endpoints, no-bus fallbacks, 400 on missing name, 404 on unregister unknown.
- ✅ 65E: `scripts/prove.py` — 148 test modules registered.
- ✅ 65F: README Phase Map updated; Phase 66 planned.

**Phase 66 — Complete.** All 150 test modules green. Sovereign Saga Orchestrator — long-running multi-step workflow engine; each step is a named callable that transforms a payload dict, output of step N becomes input of step N+1; on any failure the saga records `status="failed"` with the failing step + error and stops. Stdlib only:

- ✅ 66A: `pradyos/core/saga_orchestrator.py` — `SagaRun` dataclass (saga_id=uuid4, saga_name, steps, status pending/running/completed/failed, current_step, started_at, finished_at, payload_trace list of per-step `{step, input, output}` or `{step, input, error}`, error) with `to_dict()`; `SagaOrchestrator(HISTORY_LIMIT=200)` with `register(name, handler)` (overwrites), `unregister()` (T/F), `list_handlers()` (sorted), `run(saga_name, steps, initial_payload=None)` (creates SagaRun, snapshots handlers under lock, executes OUTSIDE the lock so re-entrant register/unregister can't deadlock; on unknown step or handler exception → records trace + status=failed + finished_at and returns immediately; chains step output → next step input; empty steps → completes immediately), `get(saga_id)` (O(1) via `_index`), `list_runs(limit=50)` (most-recent first, capped at HISTORY_LIMIT), `clear()` (count returned); thread-safe via `threading.Lock`; deque overflow drops the oldest run from index too.
- ✅ 66B: `pradyos/sovereign_web.py` directly edited (no patch script) — added `saga_orchestrator: Any | None = None` param and 3 endpoints: `POST /api/v1/sagas/run` (400 on missing name or non-list steps), `GET /api/v1/sagas?limit=N` (clamped 0–200), `GET /api/v1/sagas/{saga_id}` (404 if missing).
- ✅ 66C: `tests/test_saga_orchestrator.py` — 20 unit tests (init, register/overwrite/unregister/list-sorted, run no-steps/single-step/payload-trace-shape/multi-step-chain/all-succeed/unknown-step-fail/handler-exception-fail/stops-at-failure, get by-id/unknown, list_runs most-recent-first/limit, clear, 20 concurrent runs all findable via .get()).
- ✅ 66D: `tests/test_saga_web.py` — 10 FastAPI TestClient tests using pre-registered `double` and `add_one` step handlers; covers all 3 endpoints, no-orchestrator fallbacks, 400 on missing name/steps, empty steps completes, end-to-end POST→GET→GET-by-id flow.
- ✅ 66E: `scripts/prove.py` — 150 test modules registered.
- ✅ 66F: README Phase Map updated; Phase 67 planned.

**Phase 67 — Complete.** All 152 test modules green. Sovereign Process Manager — tracks long-running stateful process instances (business processes, not OS processes); each instance carries a user-defined state string plus a mutable context dict plus full transition history. Stdlib only:

- ✅ 67A: `pradyos/core/process_manager.py` — `HistoryEntry(at, from_state, to_state, trigger, context_snapshot)` dataclass with `to_dict()`; `ProcessInstance(process_id=uuid4, process_name, state, context, history, created_at, updated_at)` with `to_dict()`; `ProcessManager(CAPACITY=500)` with `create(name, initial_state, context=None)` (deque + O(1) `_index`, evicts oldest from both on overflow), `transition(process_id, trigger, new_state, context_patch=None)` (shallow-merges patch into context FIRST, then snapshots the *patched* context into the history entry, then updates state and updated_at; returns None for unknown id), `get(process_id)` (O(1)), `list_processes(state=None, limit=50)` (sorted by updated_at DESC, optional state filter), `delete()` (cleans both deque + index), `count(state=None)`; thread-safe via `threading.Lock`.
- ✅ 67B: `pradyos/sovereign_web.py` directly edited (no patch script) — added `process_manager: Any | None = None` param and 4 endpoints: `POST /api/v1/processes` (400 on missing name/state), `POST /api/v1/processes/{id}/transition` (400 on missing trigger/state, 404 on unknown id), `GET /api/v1/processes/{id}` (404 if missing), `GET /api/v1/processes?state=X&limit=N` (clamped 0–500).
- ✅ 67C: `tests/test_process_manager.py` — 20 unit tests (init zero count, create returns/stored/default-context/custom-context, transition returns/unknown-None/updates-state/shallow-merge/appends-history/correct-from-to/snapshot-AFTER-patch/no-patch-preserves-context, two transitions → two entries, list_processes most-recent-first/state-filter/limit, delete true/false/cleans-index, count(state) breakdown).
- ✅ 67D: `tests/test_process_web.py` — 10 FastAPI TestClient tests covering all 4 endpoints, no-manager fallbacks, 400 on missing required keys, 404 on unknown id, end-to-end create→transition→get-by-id flow.
- ✅ 67E: `scripts/prove.py` — 152 test modules registered.
- ✅ 67F: README Phase Map updated; Phase 68 planned.

**Phase 68 — Complete.** All 154 test modules green. Sovereign Scheduler — time-based job queue with one-shot and repeating jobs; tick-driven execution model resolves due jobs against a named handler registry, captures success/failure, and auto-reschedules repeating jobs by adding `interval_seconds` to `next_run_at`. Stdlib only:

- ✅ 68A: `pradyos/core/job_scheduler.py` — `Job(job_id=uuid4, name, run_at, interval_seconds, payload, status pending/running/completed/failed/cancelled, last_run_at, next_run_at, result, error, created_at)` with `to_dict()`; `Scheduler(CAPACITY=1000)` with `register_handler(name, fn)`, `schedule(name, run_at, payload=None, interval_seconds=None)` (deque-eviction syncs index), `cancel(job_id)` (True only if currently pending), `tick(now=None)` (snapshots due jobs + handlers under lock then executes OUTSIDE the lock; no-handler → status=failed with diagnostic; exception → status=failed/error=str(exc); success → status=completed/result=ret; repeating job → status reset to pending with next_run_at += interval_seconds), `get()`, `list_jobs(status=None, limit=50)` (sorted by created_at DESC), `count(status=None)`, `delete()`; thread-safe via `threading.Lock`. **Deviation:** filename is `job_scheduler.py` (not `scheduler.py`) because Phase 38's TaskScheduler already owns `pradyos/core/scheduler.py`.
- ✅ 68B: `pradyos/sovereign_web.py` directly edited (no patch script) — added `job_scheduler: Any | None = None` param and 5 endpoints: `POST /api/v1/jobs` (400 on missing name/run_at), `POST /api/v1/jobs/tick`, `GET /api/v1/jobs?status=X&limit=N` (clamped 0–1000), `GET /api/v1/jobs/{job_id}` (404 if missing), `DELETE /api/v1/jobs/{job_id}` (404 if not found or not pending). **Deviation:** URL prefix is `/api/v1/jobs/*` (not `/api/v1/scheduler/*`) because Phase 15 owns `/api/v1/scheduler/jobs` (different shape) and Phase 38 owns `/api/v1/scheduler/tick` (different scheduler).
- ✅ 68C: `tests/test_job_scheduler.py` — 20 unit tests (init zero, schedule fields/pending/next_run_at, get/unknown, cancel pending/non-pending/unknown, tick handler-called/completed/result-captured/exception-failed/error-string/no-handler-message/repeating-reschedules/interval-advances/future-not-executed, list/count by status).
- ✅ 68D: `tests/test_job_scheduler_web.py` — 10 FastAPI TestClient tests covering all 5 endpoints, no-scheduler fallbacks, 400 on missing name/run_at, 404 on unknown id, end-to-end schedule→tick→get→cancel flow.
- ✅ 68E: `scripts/prove.py` — 154 test modules registered.
- ✅ 68F: README Phase Map updated; Phase 69 planned.

**Phase 69 — Complete.** All 155 test modules green. Sovereign Signal Anomaly Detector — z-score statistical outlier detection over a named `SignalAggregator` signal. Downsamples the windowed history into 1-second buckets (the mean of all readings sharing `floor(recorded_at)`) for a sampling-rate-independent baseline, scores the most recent bucket as a z-score against the windowed population mean/stddev, and maps `|z|` to a severity label (`normal` < 2 ≤ `warning` < 3 ≤ `critical`). Pure stdlib — no numpy/scipy:

- ✅ 69A: `pradyos/core/anomaly_detector.py` — `_severity(z)` (|z|≥3 → critical, ≥2 → warning, else normal); `AnomalyResult(signal, sample_size, window, mean, stddev, latest_value, z_score, severity, computed_at)` dataclass with `to_dict()`; `AnomalyDetector(aggregator)` with `detect(signal, window=3600.0)` (filters points by `recorded_at >= now − window` via the aggregator's public `get()`; 1-second bucketing; `n==0` → all-zero `normal` result; `n<2` → no-spread `normal`; else population stddev + `z=(latest − mean)/stddev`, `0.0` when stddev is 0; mean/stddev/latest/z rounded to 6 dp), `get_cached(signal, window)`, `cache_result(result)` (insertion-order LRU, evicts oldest beyond 128); thread-safe via `threading.Lock`. **Deviation:** the literal Phase 69 brief ("Sovereign Correlation Engine") already shipped as Phase 33, and the previously-planned Circuit Breaker likewise overlapped existing work — so Phase 69 delivers a new, non-colliding Anomaly Detector that reuses the Phase 31 `SignalAggregator` without modifying it.
- ✅ 69B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase69.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged) — added `anomaly_detector: Any | None = None` param and 2 endpoints: `GET /api/v1/anomaly?signal=X&window=Y&use_cache=bool` and `POST /api/v1/anomaly` (body `{signal, window?, use_cache?}`); both return `{"error": ...}` when no detector is configured or `signal` is missing, and tag each response with `"cached"` (true only on a `use_cache` hit).
- ✅ 69C: `tests/test_anomaly_detector.py` — 20 unit tests (init; return type; missing-signal zero result; single-bucket/constant no-spread; clear positive + negative anomaly → critical; mean + population stddev; z-score formula; parametrized severity normal/warning/critical bands incl. negative z; 1-second bucketing averages same-second readings; window excludes old points; window value preserved; 6-dp rounding; `to_dict` keys; cache miss/store/retrieve; LRU eviction caps at 128; 30-thread concurrent detect/cache safety).
- ✅ 69D: `tests/test_anomaly_web.py` — 10 FastAPI TestClient tests (no-engine GET/POST errors; valid GET 200 + all fields; valid POST 200; unknown signal → sample_size 0; `use_cache` miss-then-hit; window defaults to 3600.0; window filter excludes old points).
- ✅ 69E: `scripts/prove.py` — 155 test modules registered (running total; Phase 69 appends `test_anomaly_detector.py` + `test_anomaly_web.py`).
- ✅ 69F: README Phase Map updated; Phase 70 planned.

**Phase 70 — Complete.** All 157 test modules green. Sovereign Dependency Graph — tracks directed dependencies between named components (an edge `a -> b` means "a depends on b"), stored as a forward adjacency map plus a mirror reverse map so both "what does X need?" and "who needs X?" are O(1). Pure stdlib — no third-party deps; thread-safe via a single `threading.Lock`:

- ✅ 70A: `pradyos/core/dependency_graph.py` — `CycleError(cycle)` (carries the offending node path, closed on itself); `DependencyGraph` with `add_dependency(frm, to)` (idempotent, auto-creates nodes), `remove_dependency(frm, to)` (returns whether the edge existed; nodes retained), `get_dependencies(node)` / `get_dependents(node)` (direct, sorted), `impact_score(node)` (count of transitive dependents — how far a failure ripples), `find_cycle()` (DFS back-edge search → closed cycle path or `None`), `topological_sort(start=None)` (Kahn's algorithm, dependency-first, alphabetical tie-break for determinism; restricted to a node's transitive closure when `start` is given; raises `CycleError` on cycles), `describe(node)` (JSON snapshot), `has_node` / `nodes`. **Deviation:** the literal Phase 70 brief ("Sovereign Correlation Engine") already shipped as Phase 33 — so, following the Phase 69 precedent, Phase 70 delivers a new, non-colliding Dependency Graph; the previously-planned Anomaly Watch is deferred to Phase 71.
- ✅ 70B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase70.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added `dependency_graph: Any | None = None` param and 5 endpoints: `GET /api/v1/deps/{node}` (node snapshot), `POST /api/v1/deps` (body `{from, to}`; 422 when either is missing), `DELETE /api/v1/deps/{from}/{to}`, `GET /api/v1/deps/{node}/sort` (topo sort from the node; 409 + cycle path on a cycle), and `GET /api/v1/deps/{node}/impact`; all return `{"error": ...}` when no graph is configured.
- ✅ 70C: `tests/test_dependency_graph.py` — 23 unit tests (init; add creates both nodes; dependencies/dependents; idempotent add; remove true/false + node retention; membership; unknown-node empties; linear-chain + edge-respecting + deterministic topo sort; scoped sort from a node; cycle → `CycleError` with a valid path; `find_cycle` none/simple/self-loop; impact score direct + transitive; `describe` fields; 20-thread concurrent-add safety).
- ✅ 70D: `tests/test_dependency_web.py` — 10 FastAPI TestClient tests (no-engine GET/POST errors; node info + fields; POST adds edge; POST missing field → 422; DELETE removes / non-existent → false; topo sort order; cycle → 409 with closed path; impact score).
- ✅ 70E: `scripts/prove.py` — 157 test modules registered (running total; Phase 70 appends `test_dependency_graph.py` + `test_dependency_web.py`).
- ✅ 70F: README Phase Map updated; Phase 71 planned.

**Phase 71 — Complete.** All 159 test modules green. Sovereign Anomaly Watch — a real-time anomaly-detection watchdog that polls registered service health metrics and scores the latest reading of each source with a scikit-learn `IsolationForest` (the same algorithm the hardware-intel service uses), flagging statistical outliers; thread-safe via a single `threading.Lock`:

- ✅ 71A: `pradyos/core/anomaly_watch.py` — `SourceNotFoundError(name)` (carries the offending source name); `AnomalyWatch(min_samples=10, window=256, contamination="auto", n_estimators=100, random_state=42)` with `register_source(name, metric_fn, baseline=None)` (a zero-arg `metric_fn` returns the live metric; the optional `baseline` pre-seeds the rolling window), `tick()` (polls every source, appends its reading to a bounded window, and scores the latest value once ≥ `min_samples` readings exist — returning `{"status": "warming_up"}` before that, and isolating any source whose `metric_fn` raises as `{"status": "error"}` rather than aborting the tick), `get_anomalies()` (latest results currently flagged anomalous), `get_status()` (latest per-source results), `deregister(name)` (raises `SourceNotFoundError`), `sources()` / `has_source()` / `sample_count()`, and `clear()`. **Deviation:** the README's earlier Phase 71 sketch (a z-score `AnomalyDetector` loop over `SignalAggregator`) is superseded by this brief's IsolationForest design; it ships as a new module distinct from the Phase 69 detector, so nothing is overwritten.
- ✅ 71B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase71.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added an `anomaly_watch: Any | None = None` param and 4 endpoints: `GET /api/v1/anomaly/sources` (list), `POST /api/v1/anomaly/sources` (body `{name, baseline}`; 422 when `name` is missing or `baseline` is non-numeric), `GET /api/v1/anomaly/status` (runs a tick → per-source `{"results": ...}`), and `DELETE /api/v1/anomaly/sources/{name}` (404 when unknown); all return `{"error": ...}` when no watch is configured. These sub-paths coexist with the Phase 69 `GET`/`POST /api/v1/anomaly` z-score routes without shadowing them.
- ✅ 71C: `tests/test_anomaly_watch.py` — 27 unit tests (register/list/replace/non-callable reject; warming-up before `min_samples` and scoring after; baseline seeding; configurable `min_samples`; extreme-value anomaly detection + normal-value pass; `get_anomalies` filtering; status snapshots + returned-copy isolation; empty/no-source ticks; `metric_fn` exception isolation; bounded window; `sample_count`; `clear`; `deregister` + `SourceNotFoundError` carrying the name; 10-thread concurrent register/tick safety).
- ✅ 71D: `tests/test_anomaly_watch_web.py` — 16 FastAPI TestClient tests (no-watch errors on all four routes; empty listing; register + list; missing-name / bad-baseline → 422; empty baseline; warming-up / scored-normal / scored-anomaly status; delete removes / unknown → 404; the Phase 69 `/api/v1/anomaly` route stays distinct). **Naming:** the web test is `test_anomaly_watch_web.py` because `test_anomaly_web.py` already belongs to Phase 69.
- ✅ 71E: `scripts/prove.py` — 159 test modules registered (running total; Phase 71 appends `test_anomaly_watch.py` + `test_anomaly_watch_web.py`).
- ✅ 71F: README Phase Map updated; Phase 72 planned.

**Phase 72 — Complete.** All 161 test modules green. Sovereign Bloom Filter — a space-efficient probabilistic set-membership structure: items are hashed into a fixed bit array via Kirsch–Mitzenmacher double-hashing (two 64-bit halves of one SHA-256 digest), so `contains` may false-positive but **never** false-negatives — ideal for cheap "have I seen this?" guards. Pure stdlib (`hashlib` + a `bytearray`); thread-safe via a single `threading.Lock`. **Pivot:** the previously-planned Phase 72 "Policy Engine" namespace is fully occupied by Phase 14 (`pradyos/imperium/policy_engine.py`, `/api/v1/policy/rules`, both test modules), and "Event Bus" collided with `pradyos/core/bus.py::EventBus` + the Phase 48 `/api/v1/events` event store — so, following the standing pivot precedent, Phase 72 ships a new, namespace-verified Bloom Filter.

- ✅ 72A: `pradyos/core/bloom_filter.py` — `BloomFilter(capacity=1000, error_rate=0.01)` derives the optimal bit count `m = ceil(-(n·ln p)/(ln 2)²)` and hash count `k = round((m/n)·ln 2)`; `add(item) → bool` (True when a new bit was set), `add_many(items) → int` (count newly set), `contains(item)` / `__contains__`, `clear()`, `__len__` (approx distinct added), `fill_ratio()`, `estimated_false_positive_rate()`, `stats()` (JSON snapshot), plus `capacity` / `error_rate` / `bits` / `hashes` properties. Any key type is accepted (strings hashed directly, others via `repr`). Invalid `capacity` / `error_rate` raise `ValueError`.
- ✅ 72B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase72.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `bloom_filter: Any | None = None` param and 4 endpoints: `GET /api/v1/bloom` (stats), `POST /api/v1/bloom/add` (body `{item}` or `{items: [...]}`; 422 on missing/non-string), `GET /api/v1/bloom/contains/{item}`, and `DELETE /api/v1/bloom` (clear); all return `{"error": ...}` when no filter is configured. The `/api/v1/bloom` prefix was verified free against every existing route.
- ✅ 72C: `tests/test_bloom_filter.py` — 26 unit tests (sizing from capacity/error_rate; invalid-arg `ValueError`; add new/dup; contains hit/miss + `in` operator; `add_many` counts; `len`; the no-false-negative guarantee over 500 items; empirical false-positive rate within bound; clear; stats keys/count; fill-ratio; estimated-fpp; property accessors; non-string + unicode keys; 10-thread concurrent-add safety).
- ✅ 72D: `tests/test_bloom_filter_web.py` — 14 FastAPI TestClient tests (no-filter errors on all four routes; stats keys; add single/list; missing / non-string → 422; contains hit/miss; clear resets; no-false-negative over HTTP).
- ✅ 72E: `scripts/prove.py` — 161 test modules registered (running total; Phase 72 appends `test_bloom_filter.py` + `test_bloom_filter_web.py`).
- ✅ 72F: README Phase Map updated; Phase 73 planned.

**Phase 73 — Complete.** All 163 test modules green. Sovereign Consistent Hash Ring — maps arbitrary keys to a changing set of nodes so that adding or removing a node reshuffles only that node's keys, never the rest (the consistent-hashing property). Each node is placed at `replicas` points around a 2^64 SHA-256 ring; a key is owned by the first node clockwise, located in O(log V) via `bisect`. Pure stdlib (`hashlib` + `bisect`); thread-safe via a single `threading.Lock`:

- ✅ 73A: `pradyos/core/hash_ring.py` — `NodeNotFoundError(node)` (carries the offending name); `HashRing(nodes=None, *, replicas=100)` with `add_node` (idempotent), `remove_node` (raises `NodeNotFoundError`), `get_node(key)` (owner, or `None` on an empty ring), `get_nodes(key, count)` (distinct clockwise nodes for replication), `nodes()` / `has_node()`, `distribution(keys)` (per-node key counts), `stats()` (JSON snapshot), and `clear()`. Invalid `replicas` raises `ValueError`.
- ✅ 73B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase73.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `hash_ring: Any | None = None` param and 4 endpoints: `GET /api/v1/hashring` (stats), `POST /api/v1/hashring/nodes` (body `{node}`; 422 on missing), `GET /api/v1/hashring/node/{key}` (owner lookup), and `DELETE /api/v1/hashring/nodes/{node}` (404 on unknown); all return `{"error": ...}` when no ring is configured. The `/api/v1/hashring` prefix was verified free against every existing route.
- ✅ 73C: `tests/test_hash_ring.py` — 25 unit tests (construction + invalid `replicas`; idempotent add; remove + `NodeNotFoundError` carrying the name; lookup determinism / membership; `get_nodes` distinct / cap / empty / non-positive; balanced distribution; the consistent-hashing guarantee on **both** add and remove; stats; virtual-point math; clear; 10-thread concurrency).
- ✅ 73D: `tests/test_hash_ring_web.py` — 13 FastAPI TestClient tests (no-ring errors on all four routes; stats keys; add + node_count; missing → 422; empty-ring lookup → null; member lookup; determinism; remove; unknown → 404).
- ✅ 73E: `scripts/prove.py` — 163 test modules registered (running total; Phase 73 appends `test_hash_ring.py` + `test_hash_ring_web.py`).
- ✅ 73F: README Phase Map updated; Phase 74 planned.

**Phase 74 — Complete.** All 165 test modules green. Sovereign Cardinality Estimator — a HyperLogLog sketch that counts *distinct* items in a stream using fixed memory (m = 2^precision one-byte registers), independent of stream size. Each item is hashed (SHA-1 → 64 bits); the top `precision` bits pick a register, which keeps the largest leading-zero rank seen. The estimate uses the bias-corrected harmonic-mean formula with linear-counting in the small range, for ≈1.04/√m relative error (~0.8% at precision 14). Pure stdlib (`hashlib` + `math`); thread-safe via a single `threading.Lock`:

- ✅ 74A: `pradyos/core/hyperloglog.py` — `HyperLogLog(precision=14)` with `add(item)` / `add_many(items)`, `estimate()` (rounded distinct count) / `__len__`, `merge(other)` (register-wise max union; raises `ValueError` on precision mismatch or non-HLL), `clear()`, `fill_ratio()`, `stats()` (JSON snapshot), and `precision` / `registers` properties. Any key type is accepted (strings hashed directly, others via `repr`). Invalid `precision` (outside 4–16) raises `ValueError`.
- ✅ 74B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase74.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `hyperloglog: Any | None = None` param and 4 endpoints: `GET /api/v1/cardinality` (stats), `POST /api/v1/cardinality/add` (body `{item}` or `{items: [...]}`; 422 on missing/non-string), `GET /api/v1/cardinality/estimate`, and `DELETE /api/v1/cardinality` (clear); all return `{"error": ...}` when no estimator is configured. The `/api/v1/cardinality` prefix was verified free against every existing route.
- ✅ 74C: `tests/test_hyperloglog.py` — 27 unit tests (precision/register sizing + invalid-arg `ValueError`; empty/single/duplicate counts; `__len__`; accuracy within 3% at 1k/10k/50k; determinism; low-precision survival; merge as union / disjoint / identical / commutative + mismatch & non-HLL guards; clear; fill-ratio; stats; non-string + unicode keys; 10-thread concurrency).
- ✅ 74D: `tests/test_hyperloglog_web.py` — 13 FastAPI TestClient tests (no-estimator errors on all four routes; stats keys; add single/list; missing / non-string → 422; estimate reflects adds; ≤5% accuracy over HTTP; clear resets).
- ✅ 74E: `scripts/prove.py` — 165 test modules registered (running total; Phase 74 appends `test_hyperloglog.py` + `test_hyperloglog_web.py`).
- ✅ 74F: README Phase Map updated; Phase 75 planned.

**Phase 75 — Complete.** All 167 test modules green. Sovereign Vector Clock — tracks the causal ordering of events across independent actors. Each actor bumps its own counter on a local event (`tick`); receiving a message folds in the sender's clock via element-wise max (`merge`); comparing two clocks (`compare`) reports `before` / `after` / `equal` / `concurrent` (causally independent — a conflict). Missing actors count as 0 so clocks with different actor sets compare cleanly. Pure stdlib; thread-safe via a single `threading.Lock`:

- ✅ 75A: `pradyos/core/vectorclock.py` — `VectorClock(initial=None)` with `tick(actor)` (returns the new counter), `merge(other)` (element-wise max; `ValueError` on non-VectorClock), `compare(other)` → `before|after|equal|concurrent`, `get(actor)`, `actors()`, `to_dict()` (copy), `copy()`, `clear()`, and `stats()`. Negative or non-integer initial values raise `ValueError`.
- ✅ 75B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase75.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `vectorclock: Any | None = None` param and 4 endpoints: `GET /api/v1/clocks` (state), `POST /api/v1/clocks/tick` (body `{actor}`; 422 on missing), `POST /api/v1/clocks/merge` (body `{clock}`; 422 on non-dict or bad values), and `POST /api/v1/clocks/compare` (body `{clock}` → `{relation}`); all return `{"error": ...}` when no clock is configured. The `/api/v1/clocks` prefix was verified free against every existing route.
- ✅ 75C: `tests/test_vectorclock.py` — 29 unit tests (construction + invalid-value `ValueError`; tick increments / independent actors / unknown → 0; compare equal / before / after / concurrent incl. missing-actor and mixed-lead cases; merge element-wise max / new actors / commutative / idempotent + non-VC guard; copy independence; `to_dict` isolation; clear; stats; the message-passing happens-before scenario; 10-thread exact-tick concurrency).
- ✅ 75D: `tests/test_vectorclock_web.py` — 15 FastAPI TestClient tests (no-clock errors on all four routes; state keys; tick increments / twice / missing → 422 / state reflects; merge element-wise max / non-dict → 422 / bad values → 422; compare before / concurrent / equal).
- ✅ 75E: `scripts/prove.py` — 167 test modules registered (running total; Phase 75 appends `test_vectorclock.py` + `test_vectorclock_web.py`).
- ✅ 75F: README Phase Map updated; Phase 76 planned.

**Phase 76 — Complete.** All 169 test modules green. Sovereign Frequency Sketch — a Count-Min Sketch that estimates per-item frequencies over a stream in fixed `depth × width` memory. Each item is hashed into one counter per row via Kirsch–Mitzenmacher double-hashing (two 64-bit halves of one SHA-256 digest, combined as `(h1 + row·h2) mod width`); `estimate` is the minimum across rows, so collisions can only inflate it — it **never under-counts**. Pure stdlib (`hashlib`); thread-safe via a single `threading.Lock`:

- ✅ 76A: `pradyos/core/countminsketch.py` — `CountMinSketch(width=2000, depth=5)` with `add(item, count=1)` (count must be a positive integer), `estimate(item) → int` (min across rows — an upper bound), `merge(other) → CountMinSketch` (element-wise sum into a NEW sketch; neither input mutated; `ValueError` on dimension mismatch or non-sketch), `clear()`, `stats()` (width / depth / cells / total), and `width` / `depth` properties. Invalid `width` / `depth` (≤ 0) raise `ValueError`.
- ✅ 76B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase76.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `countminsketch: Any | None = None` param and 4 endpoints: `GET /api/v1/frequency` (stats), `POST /api/v1/frequency/add` (body `{item, count=1}`; 422 on missing item or non-positive count), `POST /api/v1/frequency/estimate` (body `{item}`), and `POST /api/v1/frequency/merge` (body `{items: [...], item?}` — merges a sketch built from those items with the live one via `merge()` and reports the merged total / estimate); all return `{"error": ...}` when no sketch is configured. The `/api/v1/frequency` prefix was verified free.
- ✅ 76C: `tests/test_countminsketch.py` — 28 unit tests (dimension validation; add/estimate round-trip; frequency accumulation; `count` param; never-under-counts; absent → 0; distinct-item independence; invalid-count `ValueError`; merge returns a new summed sketch ≥ either source / commutative / non-mutating / dim-mismatch & non-sketch guards / total sum; clear; stats keys/total/cells; non-string + unicode keys; 10-thread exact-count concurrency).
- ✅ 76D: `tests/test_countminsketch_web.py` — 15 FastAPI TestClient tests (no-sketch errors on all four routes; stats keys; add single / with-count; missing item / bad count → 422; estimate round-trip / accumulation / missing → 422 / absent → 0; merge raises estimate ≥ source; merge invalid items → 422).
- ✅ 76E: `scripts/prove.py` — 169 test modules registered (running total; Phase 76 appends `test_countminsketch.py` + `test_countminsketch_web.py`).
- ✅ 76F: README Phase Map updated; Phase 77 planned.

**Phase 77 — Complete.** All 171 test modules green. Sovereign Merkle Tree — hashes an ordered list of items into a single root such that any change to any item flips the root, and membership is provable with an audit path of only ⌈log₂ n⌉ sibling hashes (without revealing the other items). Leaves are SHA-256 of each item; each level hashes adjacent pairs (`H(left || right)`), duplicating the last node on odd levels to stay balanced. Pure stdlib (`hashlib`); thread-safe via a single `threading.Lock`:

- ✅ 77A: `pradyos/core/merkle_tree.py` — `MerkleTree` with `add(item)` (leaf append; `ValueError` on None), `build()` / `root` property (hex root, or `None` when empty), `proof(item)` (audit path of `{"hash", "side"}` entries; `ValueError` if the tree is empty or the item is absent), `verify(item)` (recomputes the root from the item + its proof → bool), `clear()`, `stats()` (leaves / height / root), and `__len__`. Odd-leaf duplication keeps the tree balanced; the proof length is ⌈log₂ n⌉.
- ✅ 77B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase77.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `merkle_tree: Any | None = None` param and 4 endpoints: `GET /api/v1/merkle` (stats), `POST /api/v1/merkle/add` (body `{item}`; 422 on missing), `POST /api/v1/merkle/verify` (body `{item}` → `{verified}`), and `POST /api/v1/merkle/proof` (body `{item}` → audit path + root; 404 when the item isn't a leaf); all return `{"error": ...}` when no tree is configured. The `/api/v1/merkle` prefix was verified free.
- ✅ 77C: `tests/test_merkle_tree.py` — 28 unit tests (empty root None / stats / len; root set + SHA-256-hex + changes on add; determinism; order-sensitivity; verify added / unknown / empty across sizes 1–16; proof length = ⌈log₂ n⌉; single-leaf empty proof; proof entry shape; odd-tree proof recompute; proof unknown / empty → `ValueError`; stats keys / height / leaves; clear; add-None `ValueError`; non-string + unicode; 10-thread concurrency).
- ✅ 77D: `tests/test_merkle_tree_web.py` — 15 FastAPI TestClient tests (no-tree errors on all four routes; stats keys + empty-root null; add sets root / count; missing item → 422; verify added / unknown; proof path + root / unknown → 404 / missing → 422; add→verify→proof round-trip).
- ✅ 77E: `scripts/prove.py` — 171 test modules registered (running total; Phase 77 appends `test_merkle_tree.py` + `test_merkle_tree_web.py`).
- ✅ 77F: README Phase Map updated; Phase 78 planned.

**Phase 78 — Complete.** All 173 test modules green. Sovereign Skip List — an ordered key→value map with expected O(log n) search / insert / delete. Node heights are chosen randomly (geometric, `p=0.5`, up to `max_level=16`) so higher express lanes let a search skip large spans and drop down near the key; the bottom level is a sorted linked list, so inclusive range queries and in-order iteration come for free. Pure stdlib (`random`, seedable for determinism); thread-safe via a single `threading.Lock`:

- ✅ 78A: `pradyos/core/skiplist.py` — `SkipList(max_level=16, p=0.5, seed=None)` with `insert(key, value)` (overwrites an existing key), `search(key) → value | None`, `delete(key) → bool`, `range_query(lo, hi) → list[(key, value)]` (inclusive, ascending; empty when `lo > hi`), `items()` (ordered), `__contains__`, `__len__`, `clear()`, and `stats()` (size / level_count / max_level). `None` keys/bounds raise `ValueError`; invalid `max_level` / `p` raise `ValueError`.
- ✅ 78B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase78.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `skiplist: Any | None = None` param and 4 endpoints: `GET /api/v1/skiplist` (stats), `POST /api/v1/skiplist/insert` (body `{key, value}`; 422 on missing key), `POST /api/v1/skiplist/search` (body `{key}` → `{value, found}`), and `POST /api/v1/skiplist/range` (body `{lo, hi}` → sorted `{results, count}`); all return `{"error": ...}` when no list is configured. The `/api/v1/skiplist` prefix was verified free.
- ✅ 78C: `tests/test_skiplist.py` — 30 unit tests (`max_level` / `p` validation; insert/search round-trip; absent → None; overwrite; `__contains__` / `__len__`; arbitrary values; delete present / absent / size; ordered items after unordered insert; inclusive range / single / empty (lo>hi) / no-match / sorted; ordering invariant after 200 insert + 60 delete; 200-key searchability; clear; stats keys / size / level-bounds; None key/bound `ValueError`; 10-thread concurrency).
- ✅ 78D: `tests/test_skiplist_web.py` — 14 FastAPI TestClient tests (no-list errors on all four routes; stats keys; insert sets size; missing key → 422; search found / absent; missing key → 422; range inclusive+sorted / empty (lo>hi) / missing bounds → 422; insert→search→range round-trip).
- ✅ 78E: `scripts/prove.py` — 173 test modules registered (running total; Phase 78 appends `test_skiplist.py` + `test_skiplist_web.py`).
- ✅ 78F: README Phase Map updated; Phase 79 planned.

**Phase 79 — Complete.** All 175 test modules green. Sovereign T-Digest — estimates streaming quantiles (median, p95, p99 …) in compact, mergeable memory. Values become centroids `(mean, weight)`; a compression step (size bound `4·N·q·(1-q)/compression`) merges the bulk while keeping the tails at singleton resolution, so `percentile(0)` is the true min and `percentile(100)` the true max. Quantile lookup interpolates between centroid centres. Pure stdlib; thread-safe via a single `threading.Lock`:

- ✅ 79A: `pradyos/core/tdigest.py` — `TDigest(max_centroids=300, compression=100)` with `add(value, weight=1)`, `percentile(p)` (p ∈ [0, 100]) / `quantile(q)` (q ∈ [0.0, 1.0]), `merge(other) → TDigest` (pools and re-compresses centroids in sorted order ⇒ order-independent / commutative), `min` / `max` / `count` properties, `clear()`, and `stats()`. Non-numeric values, non-positive weights, and out-of-range q/p raise `ValueError`; `percentile` / `quantile` / `min` / `max` on an empty digest raise `ValueError`.
- ✅ 79B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase79.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `tdigest: Any | None = None` param and 4 endpoints: `GET /api/v1/tdigest` (stats), `POST /api/v1/tdigest/add` (body `{value, weight=1}`; 422 on bad input), `POST /api/v1/tdigest/percentile` (body `{q}` with q ∈ [0, 100]; 400 on an empty digest), and `POST /api/v1/tdigest/merge` (body `{values, q?}` — merges a digest of those values with the live one and reports the merged count / percentile); all return `{"error": ...}` when no digest is configured. The `/api/v1/tdigest` prefix was verified free.
- ✅ 79C: `tests/test_tdigest.py` — 30 unit tests (arg validation; empty-digest `ValueError` on percentile / quantile / min / max; count tracking; p0=min / p100=max / quantile extremes; median + p90 accuracy within tolerance; percentile↔quantile equivalence; monotonicity; single-value; weight accumulation; merge count=sum / commutative / min-max / with-empty / non-mutating / non-TDigest guard; out-of-range q/p; clear; stats).
- ✅ 79D: `tests/test_tdigest_web.py` — 16 FastAPI TestClient tests (no-digest errors on all four routes; stats keys; add count / weight; bad value & weight → 422; percentile extremes / middle / out-of-range → 422 / empty → 400; merge count + percentile / invalid values → 422; add→percentile round-trip).
- ✅ 79E: `scripts/prove.py` — 175 test modules registered (running total; Phase 79 appends `test_tdigest.py` + `test_tdigest_web.py`).
- ✅ 79F: README Phase Map updated; Phase 80 planned.

**Phase 80 — Complete.** All 177 test modules green. Sovereign Fenwick Tree — a binary indexed tree answering prefix-sum queries and point updates both in O(log n) by exploiting the binary structure of indices (each slot covers a range of length `i & -i`; updates walk up by adding that bit, prefix sums walk down by subtracting it). 1-indexed; `range_sum(lo, hi) = prefix_sum(hi) - prefix_sum(lo-1)`. Pure stdlib; thread-safe via a single `threading.Lock`:

- ✅ 80A: `pradyos/core/fenwick.py` — `FenwickTree(size)` with `update(i, delta)` (1-indexed; int or float, may be negative), `prefix_sum(i)` (sum of 1..i; `prefix_sum(0)=0`), `range_sum(lo, hi)` (inclusive), `point_query(i)` (value at i), `resize(new_size)` (preserves the overlap), `clear()`, `size` property, and `stats()` (size / total). Out-of-bounds indices, `lo > hi`, non-integer indices, non-numeric deltas, and `size < 1` raise `ValueError`.
- ✅ 80B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase80.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `fenwick: Any | None = None` param and 4 endpoints: `GET /api/v1/fenwick` (stats), `POST /api/v1/fenwick/update` (body `{index, delta}`), `POST /api/v1/fenwick/query` (body `{lo, hi}` → range sum), and `POST /api/v1/fenwick/point` (body `{index}` → value); invalid input maps the core's `ValueError` to 422; all return `{"error": ...}` when no tree is configured. The `/api/v1/fenwick` prefix was verified free.
- ✅ 80C: `tests/test_fenwick.py` — 30 unit tests (size validation; update/prefix-sum round-trip; `prefix_sum(0)=0`; cumulative sums; range_sum inclusive / single / full / identity; point_query after updates; accumulation; negative + float deltas; resize grow / shrink; clear; stats; out-of-bounds & lo>hi & bad-delta `ValueError`; 100-update correctness vs a reference array; million-element O(log n) timing; 10-thread exact-update concurrency).
- ✅ 80D: `tests/test_fenwick_web.py` — 15 FastAPI TestClient tests (no-tree errors on all four routes; stats keys; update reflected in total / negative delta / out-of-bounds → 422 / bad delta → 422; range-sum query / out-of-bounds → 422 / lo>hi → 422; point value / out-of-bounds → 422; update→query→point round-trip).
- ✅ 80E: `scripts/prove.py` — 177 test modules registered (running total; Phase 80 appends `test_fenwick.py` + `test_fenwick_web.py`).
- ✅ 80F: README Phase Map updated; Phase 81 planned.

**Phase 81 — Complete.** All 179 test modules green. Sovereign Segment Tree — O(log n) range queries (sum / min / max, fixed at construction) with point updates over a fixed-size array, more general than a Fenwick tree. Implemented as an iterative bottom-up tree (a flat `2·n` array, leaves in `[n, 2n)`) for cache-friendly speed; sum/min/max are commutative + associative so the bottom-up combine order is correct. Pure stdlib; thread-safe via a single `threading.Lock`:

- ✅ 81A: `pradyos/core/segtree.py` — `SegmentTree(size, mode='sum')` (mode ∈ sum/min/max) with `update(i, val)` (1-indexed point *set*; int/float, may be negative), `query(lo, hi)` (inclusive range aggregate), `point_query(i)`, `resize(new_size)` (preserves the overlap, clears the extension), `clear()`, `size` / `mode` properties, and `stats()` (size / mode / aggregate). Invalid size, invalid mode, out-of-bounds indices, `lo > hi`, and non-numeric values raise `ValueError`. **Note:** uses the iterative `2·n` layout rather than the textbook recursive `4·n` because recursive Python missed the O(log n) latency budget on n=1M (≈0.14 s vs ≈0.08 s).
- ✅ 81B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase81.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `segtree: Any | None = None` param and 4 endpoints: `GET /api/v1/segtree` (stats), `POST /api/v1/segtree/update` (body `{index, value}`), `POST /api/v1/segtree/query` (body `{lo, hi}` → `{mode, result}`), and `POST /api/v1/segtree/point` (body `{index}` → value); invalid input maps the core's `ValueError` to 422; all return `{"error": ...}` when no tree is configured. The `/api/v1/segtree` prefix was verified free.
- ✅ 81C: `tests/test_segtree.py` — 31 unit tests (size/mode validation; sum/min/max correctness vs a reference array; point-query match; set-overwrite; boundaries i=1 / i=n / single / full; negative + float values; resize grow / shrink / mode-preserve; mode isolation; clear; stats; out-of-bounds & lo>hi & bad-value `ValueError`; O(log n) 20k-updates-on-n=1M timing).
- ✅ 81D: `tests/test_segtree_web.py` — 18 FastAPI TestClient tests (no-tree errors on all four routes; stats keys + mode; update reflected / out-of-bounds → 422 / bad value → 422; query in sum / min / max modes / boundary / out-of-bounds → 422 / lo>hi → 422; point value / out-of-bounds → 422; round-trip; plus a regression check that the Phase 77–80 routes are still live).
- ✅ 81E: `scripts/prove.py` — 179 test modules registered (running total; Phase 81 appends `test_segtree.py` + `test_segtree_web.py`).
- ✅ 81F: README Phase Map updated; Phase 82 planned.

**Phase 82 — Complete.** All 181 test modules green. Sovereign Union-Find — a disjoint-set forest tracking a partition of n elements with effectively constant-time connectivity queries. Union by rank keeps trees shallow and path-halving `find` flattens them as a side effect of the query, giving the near-O(α(n)) bound (α ≤ 4 for any practical n). 1-indexed. Pure stdlib; thread-safe via a single `threading.Lock`:

- ✅ 82A: `pradyos/core/unionfind.py` — `UnionFind(size)` with `union(a, b)` (returns whether a merge happened; a self-union or an already-connected union is a no-op), `find(a)` (iterative path halving), `connected(a, b)`, `component_size(a)`, `component_count()`, `reset()`, `size` property, and `stats()` (size / components / largest_component). Out-of-bounds and non-integer elements raise `ValueError`. Rank (a height bound) drives unions; element counts are tracked separately for `component_size`.
- ✅ 82B: `pradyos/sovereign_web.py` patched additively via `scripts/patch_web_phase82.py` (never rewritten; the DASHBOARD_HTML line is asserted byte-length-unchanged; an `ast.parse` gate refuses to write broken code) — added a `unionfind: Any | None = None` param and 4 endpoints: `GET /api/v1/unionfind` (stats), `POST /api/v1/unionfind/union` (body `{a, b}` → `{united, components}`), `POST /api/v1/unionfind/find` (body `{a}` → `{root, component_size}`), and `POST /api/v1/unionfind/connected` (body `{a, b}` → `{connected}`); invalid input maps the core's `ValueError` to 422; all return `{"error": ...}` when no structure is configured. The `/api/v1/unionfind` prefix was verified free.
- ✅ 82C: `tests/test_unionfind.py` — 30 unit tests (size validation; initial count; union return value / self-union & redundant-union no-ops; find singleton; connected / transitivity / shared-root; component-count decrement; component-size growth; union-all-into-one; reset; correctness vs a reference DSU; path-compression correctness; stats; boundaries i=1 / i=n; out-of-bounds & non-integer `ValueError`; O(α(n)) 100k-ops-on-n=1M timing; 10-thread concurrency).
- ✅ 82D: `tests/test_unionfind_web.py` — 16 FastAPI TestClient tests (no-structure errors on all four routes; stats keys; union merges / decrements / already-connected → false / self → no-op / out-of-bounds → 422; find root + size / out-of-bounds → 422; connected true / false / out-of-bounds → 422; transitivity via sequential unions; plus a regression check that the Phase 77–81 routes are still live).
- ✅ 82E: `scripts/prove.py` — 181 test modules registered (running total; Phase 82 appends `test_unionfind.py` + `test_unionfind_web.py`).
- ✅ 82F: README Phase Map updated; Phase 83 planned.

**Phase 83 — Planned.** Sovereign Trie — a prefix tree for fast string insertion, exact-match lookup, and prefix queries (autocomplete / "starts-with"); `Trie` with `insert(word)` / `search(word)` / `starts_with(prefix)` / `count_prefix(prefix)` / `clear()`, exposed at `/api/v1/trie`; stdlib only; thread-safe via `threading.Lock`. (Namespace verified free on `origin/main`.)

---

## PradyOS v0.41.0 — Self-Driving

**99 test modules. 41 phases. Stdlib + asyncio only.**

A fully autonomous, self-driving OS kernel built in Python, with observe → alert → plan → react → heal → schedule → persist → remember → control-plane → heartbeat capabilities. The OS now drives itself — `HeartbeatLoop` ticks `ControlPlane` on a fixed cadence, which in turn ticks the scheduler, healer, and reactor in sequence. No external orchestrator needed.

The OS observes its own metrics (`SignalAggregator`), detects thresholds (`WatchpointSystem`), correlates signals (`CorrelationEngine`), records every decision into a cryptographically chained ledger (`DecisionJournal`), reacts to alerts via rules (`ReactorEngine`), self-heals degraded components (`HealingMonitor`), schedules its own work (`TaskScheduler`), persists state across restarts (`SnapshotStore` + `StateManager`), remembers context with TTLs (`MemoryStore`), wires it all together (`SovereignBus`), exposes a unified introspection layer (`ControlPlane`), and drives itself forward through an async loop (`HeartbeatLoop`).

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
  scheduler methods, cron parsing, clock injection, bus event payload, 