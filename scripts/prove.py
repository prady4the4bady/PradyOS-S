#!/usr/bin/env python3
"""PRADY OS — Repository Proving Ground: local validation runner.

Windows-safe pytest runner that:
  - Detects the correct Python/pytest executable (venv-aware)
  - Checks for common Windows environment issues before running
  - Runs each test module independently, printing PASS/FAIL per module
  - Prints a final summary table
  - Exits 0 only when every module passes; 1 on any failure

Usage
-----
    python scripts/prove.py [--module tests/test_foo.py] [--fast] [--verbose]

Options
    --module  Run only the specified module (repeatable)
    --fast    Stop on first failure (pytest -x)
    --verbose Show full pytest output even on pass
    --no-color Disable color output (for CI pipes without ANSI support)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

# Test modules in the order they should be validated
DEFAULT_MODULES: list[str] = [
    # Phase 1
    "tests/test_core.py",
    "tests/test_titan_ops.py",
    "tests/test_imperium.py",
    "tests/test_aurora_throne.py",
    "tests/test_proving_ground.py",
    "tests/test_warden_grid.py",
    "tests/test_integration.py",
    # Phase 2
    "tests/test_oracle.py",
    "tests/test_memory_citadel.py",
    "tests/test_campaign.py",
    # Phase 3
    "tests/test_sovereign_cli.py",
    "tests/test_campaign_scheduler.py",
    "tests/test_oracle_live.py",
    # Phase 4
    "tests/test_campaign_titan_bridge.py",
    "tests/test_memory_feedback.py",
    "tests/test_sovereign_web.py",
    "tests/test_proving_ground_ci.py",
    "tests/test_warden_phase4.py",
    # Phase 5
    "tests/test_snapshot.py",
    "tests/test_healthcheck.py",
    "tests/test_watchdog.py",
    "tests/test_sovereign_repl.py",
    "tests/test_campaign_analytics.py",
    # Phase 6
    "tests/test_audit.py",
    "tests/test_retry.py",
    "tests/test_metrics.py",
    "tests/test_config.py",
    "tests/test_campaign_archiver.py",
    # Phase 7 — Sovereign Convergence
    "tests/test_audit_hooks.py",
    "tests/test_metrics_hooks.py",
    "tests/test_retry_hooks.py",
    "tests/test_advisor.py",
    "tests/test_config_watcher.py",
    "tests/test_repl_ext.py",
    "tests/test_deploy.py",
    # Phase 8
    "tests/test_oracle_daemon.py",
    "tests/test_admission_bridge.py",
    # Phase 10
    "tests/test_redis_bus.py",
    # Phase 11
    "tests/test_self_heal.py",
    # Phase 12
    "tests/test_dashboard.py",
    "tests/test_dashboard_web.py",
    # Phase 13
    "tests/test_campaign_monitor.py",
    "tests/test_campaign_monitor_web.py",
    # Phase 14
    "tests/test_policy_engine.py",
    "tests/test_policy_web.py",
    # Phase 15
    "tests/test_sovereign_scheduler.py",
    "tests/test_scheduler_web.py",
    # Phase 16
    "tests/test_telemetry.py",
    "tests/test_telemetry_web.py",
    # Phase 17
    "tests/test_memorygraph.py",
    "tests/test_memorygraph_web.py",
    # Phase 18
    "tests/test_ledger.py",
    "tests/test_ledger_web.py",
    # Phase 19
    "tests/test_intent_engine.py",
    "tests/test_intent_web.py",
    # Phase 20
    "tests/test_audit_ui.py",
    "tests/test_audit_web.py",
    # Phase 21
    "tests/test_config_hot_reload.py",
    "tests/test_config_reload_web.py",
    # Phase 22
    "tests/test_metrics_registry.py",
    "tests/test_metrics_web.py",
    # Phase 23
    "tests/test_rate_limiter.py",
    "tests/test_rate_limit_web.py",
    # Phase 24
    "tests/test_health_scorecard.py",
    "tests/test_health_web.py",
    # Phase 25
    "tests/test_audit_replay.py",
    "tests/test_audit_replay_web.py",
    # Phase 26
    "tests/test_plugin_sandbox.py",
    "tests/test_plugin_web.py",
    # Phase 27
    "tests/test_bus_inspector.py",
    "tests/test_bus_inspector_web.py",
]

# ANSI color codes — disabled on Windows if ANSI not supported
_ANSI = sys.platform != "win32" or os.environ.get("TERM") or os.environ.get("ANSICON")
GREEN  = "\033[92m" if _ANSI else ""
RED    = "\033[91m" if _ANSI else ""
YELLOW = "\033[93m" if _ANSI else ""
CYAN   = "\033[96m" if _ANSI else ""
DIM    = "\033[2m"  if _ANSI else ""
BOLD   = "\033[1m"  if _ANSI else ""
RESET  = "\033[0m"  if _ANSI else ""


# ---------------------------------------------------------------------------
# Python / pytest detection
# ---------------------------------------------------------------------------

def _is_runnable(path: Path) -> bool:
    """Return True if path exists AND can actually run on this platform.

    On Linux/macOS: reject .exe files (Windows PE binaries cannot exec).
    On Windows: existence is sufficient (the OS handles extension dispatch).
    """
    if not path.exists():
        return False
    if sys.platform == "win32":
        return True  # Windows: existence is enough
    if path.suffix.lower() == ".exe":
        return False  # Windows PE on POSIX — never runnable natively
    return os.access(path, os.X_OK)


def find_python() -> str:
    """Return the Python executable to use, venv-aware.

    Candidate order respects the current platform: POSIX paths are tried
    before Windows .exe paths on Linux/macOS, and vice versa on Windows.
    """
    is_win = sys.platform == "win32"

    if is_win:
        _rel_order = ("Scripts/python.exe", "Scripts/python", "bin/python")
    else:
        _rel_order = ("bin/python", "bin/python3", "Scripts/python.exe", "Scripts/python")

    # 1. Active venv (set by activate scripts)
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        for rel in _rel_order:
            c = Path(venv) / rel
            if _is_runnable(c):
                return str(c)

    # 2. .venv or venv adjacent to project root
    for venv_dir in (".venv", "venv", ".env", "env"):
        venv_path = ROOT / venv_dir
        if venv_path.is_dir():
            for rel in _rel_order:
                c = venv_path / rel
                if _is_runnable(c):
                    return str(c)

    # 3. Fall back to the interpreter running this script (always correct)
    return sys.executable


def find_pytest(python: str) -> list[str]:
    """Return the pytest invocation as a list of args.

    Prefers ``python -m pytest`` which works regardless of PATH.
    """
    return [python, "-m", "pytest"]


# ---------------------------------------------------------------------------
# Pre-flight Windows checks
# ---------------------------------------------------------------------------

def preflight_checks() -> list[str]:
    """Return a list of warning strings (empty = all clear)."""
    warnings: list[str] = []

    if sys.platform == "win32":
        # Long path support check
        try:
            import winreg  # noqa: PLC0415
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\FileSystem",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
                if val != 1:
                    warnings.append(
                        "Windows long path support is DISABLED. "
                        "Enable it via Group Policy or HKLM\\SYSTEM\\...\\FileSystem\\LongPathsEnabled=1"
                    )
        except Exception:  # noqa: BLE001
            pass

        py_ver = sys.version_info
        if py_ver < (3, 10):
            warnings.append(
                f"Python {py_ver.major}.{py_ver.minor} detected — PRADY OS requires >= 3.10"
            )

        python = find_python()
        result = subprocess.run(
            [python, "-c", "import pytest; print(pytest.__version__)"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            warnings.append(
                f"pytest not importable via {python}. "
                "Run: pip install pytest --break-system-packages"
            )

        if " " in str(ROOT):
            warnings.append(
                f"Project root path contains spaces: {ROOT}\n"
                "  Some subprocesses may fail. Consider moving to a space-free path."
            )

    return warnings


# ---------------------------------------------------------------------------
# Module runner
# ---------------------------------------------------------------------------

def run_module(
    pytest_cmd: list[str],
    module_path: str,
    fast: bool = False,
    verbose: bool = False,
    extra_args: list[str] | None = None,
) -> tuple[bool, float, str]:
    """Run a single test module with pytest.

    Returns (passed: bool, duration_sec: float, output: str).
    """
    full_path = ROOT / module_path
    if not full_path.exists():
        return False, 0.0, f"MODULE NOT FOUND: {full_path}"

    cmd = list(pytest_cmd) + ["--tb=short", "-q", "--no-header"]
    if fast:
        cmd.append("-x")
    cmd.append(str(full_path))
    if extra_args:
        cmd.extend(extra_args)

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )
        duration = time.monotonic() - t0
        output = result.stdout + result.stderr
        passed = result.returncode == 0
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - t0
        output = "TIMEOUT: test module exceeded 120 s"
        passed = False
    except FileNotFoundError as e:
        duration = time.monotonic() - t0
        output = f"COMMAND NOT FOUND: {e}"
        passed = False

    return passed, duration, output


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

def _module_label(path: str) -> str:
    return Path(path).stem


def print_preflight(warnings: list[str]) -> None:
    if not warnings:
        print(f"{GREEN}✓ Pre-flight checks passed{RESET}")
        return
    print(f"{YELLOW}⚠ Pre-flight warnings:{RESET}")
    for w in warnings:
        print(f"  {YELLOW}•{RESET} {w}")
    print()


def print_result(label: str, passed: bool, duration: float, output: str, verbose: bool) -> None:
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    timing = f"{DIM}{duration:.2f}s{RESET}"
    print(f"  {status}  {BOLD}{label:<40}{RESET}  {timing}")
    if not passed or verbose:
        if output.strip():
            for line in output.splitlines()[-50:]:
                print(f"        {DIM}{line}{RESET}")


def print_summary(results: list[tuple[str, bool, float]]) -> None:
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed
    total_time = sum(d for _, _, d in results)

    print()
    print(f"{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}PROVING GROUND — SUMMARY{RESET}")
    print(f"{'─' * 60}")
    for label, ok, dur in results:
        icon = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {icon}  {label:<40}  {DIM}{dur:.2f}s{RESET}")
    print(f"{'─' * 60}")

    if failed == 0:
        print(f"{GREEN}{BOLD}ALL {total} MODULE(S) PASSED{RESET}  "
              f"{DIM}({total_time:.1f}s total){RESET}")
    else:
        print(f"{RED}{BOLD}{failed}/{total} MODULE(S) FAILED{RESET}  "
              f"{DIM}({total_time:.1f}s total){RESET}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prove",
        description="PRADY OS Proving Ground — local test validation runner",
    )
    parser.add_argument(
        "--module", "-m", action="append", dest="modules",
        help="test module path to run (default: all); repeatable",
    )
    parser.add_argument("--fast", "-f", action="store_true",
                        help="stop on first test failure within each module")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="always print full pytest output (not just on failure)")
    parser.add_argument("--no-color", action="store_true",
                        help="disable ANSI color codes")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="skip Windows pre-flight environment checks")
    args = parser.parse_args(argv)

    if args.no_color:
        global GREEN, RED, YELLOW, CYAN, DIM, BOLD, RESET
        GREEN = RED = YELLOW = CYAN = DIM = BOLD = RESET = ""

    print(f"\n{BOLD}{CYAN}PRADY OS — PROVING GROUND{RESET}")
    print(f"{DIM}Project root: {ROOT}{RESET}")
    print()

    # Pre-flight
    if not args.skip_preflight:
        warnings = preflight_checks()
        print_preflight(warnings)
    else:
        print(f"{DIM}(pre-flight skipped){RESET}")

    python = find_python()
    pytest_cmd = find_pytest(python)
    print(f"{DIM}Python: {python}{RESET}")
    print(f"{DIM}Pytest: {' '.join(pytest_cmd)}{RESET}")
    print()

    modules = args.modules or DEFAULT_MODULES

    # Filter to modules that exist
    existing = []
    skipped = []
    for m in modules:
        if (ROOT / m).exists():
            existing.append(m)
        else:
            skipped.append(m)

    if skipped:
        print(f"{YELLOW}Skipping missing modules:{RESET}")
        for m in skipped:
            print(f"  {DIM}(not found) {m}{RESET}")
        print()

    if not existing:
        print(f"{RED}No test modules found. Aborting.{RESET}")
        return 1

    print(f"Running {len(existing)} module(s)...\n")

    results: list[tuple[str, bool, float]] = []
    any_failed = False

    for module in existing:
        label = _module_label(module)
        passed, duration, output = run_module(
            pytest_cmd, module, fast=args.fast, verbose=args.verbose
        )
        print_result(label, passed, duration, output, args.verbose)
        results.append((label, passed, duration))
        if not passed:
            any_failed = True

    print_summary(results)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
