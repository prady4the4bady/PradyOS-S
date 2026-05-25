# PRADY OS — Repository Proving Ground

## What Is This?

The **Proving Ground** is PRADY OS's constitutional admission gate for all code before it runs on the Sovereign's machine. Every repository that IMPERIUM considers executing must pass four sequential checks:

1. **Constitutional Scan** — static analysis for patterns that would breach the OS constitution (bypassing TITAN OPS, hard-coded credentials, privileged syscalls)
2. **Dependency Audit** — manifest inspection for known typosquatting / supply-chain attack packages
3. **Test Execution** — runs the repo's own test suite in a sandboxed workspace
4. **Admission Verdict** — `ADMITTED`, `QUARANTINED`, or `REJECTED`

The `scripts/prove.py` runner applies the same gate to PRADY OS itself.

---

## Local CI Workflow

### Quick start (Windows, PowerShell 7)

```powershell
# From the project root
python scripts/prove.py
```

### First time — create a venv

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### Run all modules

```powershell
python scripts/prove.py
```

Output per module:

```
  PASS  test_core                                   0.41s
  PASS  test_titan_ops                              1.23s
  FAIL  test_imperium                               0.87s
        <truncated pytest output>
```

Final summary:

```
────────────────────────────────────────────────────────────
PROVING GROUND — SUMMARY
────────────────────────────────────────────────────────────
  ✓  test_core                                   0.41s
  ✗  test_imperium                               0.87s
────────────────────────────────────────────────────────────
1/2 MODULE(S) FAILED  (1.3s total)
```

### Run a single module

```powershell
python scripts/prove.py --module tests/test_aurora_throne.py
```

### Stop on first failure

```powershell
python scripts/prove.py --fast
```

### Show full pytest output even on pass

```powershell
python scripts/prove.py --verbose
```

### Disable ANSI colors (for CI pipes)

```powershell
python scripts/prove.py --no-color
```

---

## Python Detection

`prove.py` resolves the Python interpreter in this order:

1. `$VIRTUAL_ENV/Scripts/python.exe` — active venv (set by `Activate.ps1`)
2. `.venv/Scripts/python.exe` — `.venv` adjacent to project root
3. `venv/Scripts/python.exe` — `venv` adjacent to project root
4. `sys.executable` — the interpreter currently running `prove.py`

No hard-coded `/usr/bin/python3` paths. Works on Windows 11 and Linux.

---

## Pre-flight Checks (Windows)

On Windows, `prove.py` runs pre-flight checks before executing tests:

| Check | Consequence if fails |
|-------|---------------------|
| Long path support enabled | Warning — some file operations may silently truncate |
| Python >= 3.10 | Warning — some syntax will fail |
| `pytest` importable via detected Python | Warning — tests cannot run |
| Project root has no spaces | Warning — subprocesses may misbehave |

Warnings are printed but do not abort the run. Disable with `--skip-preflight`.

---

## Constitutional Scanner Reference

The `pradyos.proving_ground.scanner` module scans Python source files for violations:

### HARD violations → automatic `REJECTED`

| Pattern | Reason |
|---------|--------|
| `os.system(...)` | Bypasses TITAN OPS execution plane |
| `subprocess.call/run/Popen/...` | Bypasses TITAN OPS |
| `-----BEGIN PRIVATE KEY-----` literal | Hard-coded private key |
| Blocked imports: `ctypes`, `cffi`, `winreg`, `resource` | Native FFI — can bypass constitutional containment |

### SOFT violations → automatic `QUARANTINED`

| Pattern | Reason |
|---------|--------|
| `eval(...)` | Arbitrary code execution |
| `exec(...)` | Arbitrary code execution |
| `__import__(...)` | Dynamic import bypass |
| `setuid(...)` / `seteuid(...)` | Privilege escalation |
| `socket.AF_PACKET` / `socket.SOCK_RAW` | Raw socket creation |
| Hard-coded credential literals | `password = "secret123"` pattern |

### Warnings (advisory — do not block admission)

| Pattern | Reason |
|---------|--------|
| `pickle.loads(...)` | Unsafe deserialization |
| `yaml.load(...)` without Loader | Arbitrary code execution risk |
| `# noqa S###` | Bandit suppression — suspicious |
| Network imports: `socket`, `requests`, `httpx`, etc. | Should route via ORACLE |

---

## Admission Pipeline API

```python
from pradyos.proving_ground.pipeline import AdmissionPipeline

pipeline = AdmissionPipeline()
verdict = pipeline.admit("https://github.com/example/myrepo", ref="main")

print(verdict.status)   # ADMITTED | QUARANTINED | REJECTED
print(verdict.reason)   # human-readable explanation
print(verdict.test_run) # TestRun dataclass with exit_code, stdout_tail, etc.
```

### Register with IMPERIUM

```python
from pradyos.imperium.kernel import Imperium
from pradyos.proving_ground.pipeline import AdmissionPipeline

kern = Imperium()
pipeline = AdmissionPipeline()
pipeline.register_with(kern)  # registers "proving_ground.admit" handler

kern.submit(ImperiumTask(
    kind="proving_ground.admit",
    intent="admit myrepo",
    payload={"repo_url": "https://github.com/example/myrepo", "ref": "main"},
))
kern.run_one()
```

---

## Admission Verdict States

| State | Meaning |
|-------|---------|
| `ADMITTED` | All checks passed — safe to execute |
| `QUARANTINED` | SOFT violation, test failure, or dependency flag — human review required |
| `REJECTED` | HARD constitutional violation — execution permanently blocked |
| `PENDING` | Pipeline still running |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All test modules passed |
| `1` | One or more modules failed, or no modules found |

---

## Architecture

```
scripts/prove.py              ← local CI entry point
pradyos/proving_ground/
  __init__.py
  pipeline.py                 ← AdmissionPipeline orchestrator
  scanner.py                  ← Constitutional + dependency scanner
  verdict.py                  ← AdmissionVerdict, TestRun, ConstitutionScan dataclasses
tests/
  test_proving_ground.py      ← 13 tests covering scanner, pipeline, bus events
```

The pipeline runs clone → scan → audit → test → verdict in sequence. Each stage writes to the `AuditLog` (attributable, rollback-aware) and the final verdict is published on the `EventBus` as `proving_ground.verdict`.

---

## Governing Laws (Constitution §I)

1. **THE MACHINE OWNS EXECUTION.** The Proving Ground admits or blocks code — it never silently allows.
2. **Every verdict is logged** in the `AuditLog` with `agent_id = "proving_ground"`, correlation ID, and full `AdmissionVerdict` payload.
3. **REJECTED is permanent** within a session — there is no force-admit API. New projects require Sovereign approval via IMPERIUM.
4. **Dependency audit flags are advisory** (→ `QUARANTINED`) but the Sovereign must explicitly un-quarantine.
5. **The scanner cannot be silenced** by `# noqa` in the scanned repo — those annotations are themselves flagged as warnings.
