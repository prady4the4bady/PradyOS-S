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

**Phase 36 — Planned.** Sovereign State Persistence — the OS survives restarts: a StateManager wraps the SnapshotStore and provides save_state(module, key, data) and load_state(module, key) helpers; on first boot it checks for existing snapshots and restores them; a ShutdownHook registers cleanup callables that are called in order when os_shutdown() is invoked; exposes POST /api/v1/os/shutdown (calls all shutdown hooks, saves final state snapshot for each registered module), GET /api/v1/os/state/{module} (list saved state keys for a module), GET /api/v1/os/state/{module}/{key} (retrieve latest snapshot); stdlib only.

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