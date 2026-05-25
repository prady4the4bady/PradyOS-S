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
  (`/oracle/status` and import-probe respectively), plus fleet-wide
  `cap_drop: [ALL]`, `security_opt: no-new-privileges:true`,
  `read_only: true`, `tmpfs: /tmp`, and a single named volume
  `pradyos-var` for audit log + state persistence. Secrets managed via
  `deploy/secrets.env` (template at `deploy/secrets.env.example`).
- ✅ 9C: `tests/test_deploy.py` extended with 28 new assertions covering
  new systemd units, Docker hardening directives, oracle/admission
  service definitions, and healthcheck presence. All 37 modules remain green.
- ✅ 9D: README updated.

### Systemd deployment (Sovereign build)

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
    pradyos-titan.service \
    pradyos-warden.service \
    pradyos-imperium.service \
    pradyos-oracle.service \
    pradyos-admission.service
```

The `pradyos-throne.service` is a *session* unit — it is launched on
Sovereign login, not enabled as a system daemon.

### Docker production stack (Phase 9)

```bash
cp deploy/secrets.env.example deploy/secrets.env
# edit deploy/secrets.env with your Ollama URL, log level, etc.
docker compose -f deploy/docker-compose.yml up --build sovereign oracle admission
```

Healthchecks are wired to:
- `sovereign` → `GET /api/metrics` on port 8000
- `oracle` → `GET /oracle/status` on port 11435
- `admission` → Python import probe (`import pradyos.oracle.admission_bridge`)

### Phase Map

| Phase | Name | Status |
|-------|------|--------|
| 0 | Substrate (TITAN, WARDEN, IMPERIUM, THRONE) | ✅ Complete |
| 1 | Oracle AI Core + Planner | ✅ Complete |
| 2 | Memory Citadel | ✅ Complete |
| 3 | Campaign Engine | ✅ Complete |
| 4 | Warden Phase 4 | ✅ Complete |
| 5 | Sovereign Web + CLI + REPL | ✅ Complete |
| 6 | Snapshot, Healthcheck, Watchdog | ✅ Complete |
| 7 | Audit Hooks, Metrics Hooks, Retry Hooks, Config Watcher | ✅ Complete |
| 8 | Autonomous Proposal Loop + Admission Bridge | ✅ Complete |
| 9 | Deployment (systemd hardening + Docker hardening) | ✅ Complete |
| 10 | Self-healing (auto-rollback, quarantine enforcement) | 🔲 Planned |
