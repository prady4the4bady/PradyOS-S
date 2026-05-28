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

**Phase 55 — Planned.** Sovereign BulkheadPool — fixed-capacity thread-pool isolation per service; BulkheadPool(name, max_workers=4, queue_depth=8) wraps concurrent.futures.ThreadPoolExecutor; submit(name, fn, *args, **kwargs) → Future; if pool is at capacity AND queue is full, raise BulkheadRejectedError immediately (never block); track submitted, completed, rejected, and active counts per pool; get_stats(name) returns {name, max_workers, queue_depth, submitted, completed, rejected, active}; reset_stats(name); list_pools(); exposes GET /api/v1/bulkheads (list all pools + stats), POST /api/v1/bulkheads (create pool: body={name, max_workers?, queue_depth?}), GET /api/v1/bulkheads/{name} (stats), POST /api/v1/bulkheads/{name}/submit (body={sleep?} — submits a configurable-sleep no-op task for testing); stdlib only (concurrent.futures allowed); 20 unit + 10 web tests.

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