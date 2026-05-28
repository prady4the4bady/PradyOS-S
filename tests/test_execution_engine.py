"""Phase 44C — 20 tests for pradyos.core.execution_engine.ExecutionEngine.

Cross-platform: uses sys.executable (Python) as the test command instead
of `echo`, since Windows doesn't have a real echo binary.
"""
from __future__ import annotations

import shlex
import sys
import threading
import time
import uuid

import pytest

from pradyos.core.execution_engine import (
    ExecutionEngine,
    ExecutionResult,
    ExecutionStatus,
)
from pradyos.core.approval_queue import ApprovalEntry, ApprovalStatus
from pradyos.core.decision_journal import DecisionJournal


# ── helpers ───────────────────────────────────────────────────────────────────

# Use a forward-slash path so shlex.split parses it cleanly on Windows
PYBIN = sys.executable.replace("\\", "/")


def _entry(action: str, status: ApprovalStatus = ApprovalStatus.APPROVED) -> ApprovalEntry:
    return ApprovalEntry(
        id=uuid.uuid4().hex,
        action=action,
        risk_level="low",
        payload={},
        reason=None,
        status=status,
        requested_at=time.time(),
    )


def _py_action(code: str) -> str:
    """Build a `<python> -c "<code>"` action string."""
    return f'{PYBIN} -c "{code}"'


# ── init / status ─────────────────────────────────────────────────────────────

def test_init_empty_history():
    eng = ExecutionEngine(allowlist=["x"])
    assert eng._history == []


def test_status_has_required_keys():
    eng = ExecutionEngine(allowlist=["x"])
    s = eng.status()
    for key in ("allowlist", "total_runs", "last_status"):
        assert key in s


def test_status_total_runs_zero_initially():
    eng = ExecutionEngine(allowlist=["x"])
    assert eng.status()["total_runs"] == 0


# ── status check ──────────────────────────────────────────────────────────────

def test_run_pending_returns_blocked():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("print('x')"), status=ApprovalStatus.PENDING)
    result = eng.run(entry)
    assert result.status == ExecutionStatus.BLOCKED
    assert eng.status()["total_runs"] == 0


def test_run_rejected_returns_rejected():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("print('x')"), status=ApprovalStatus.REJECTED)
    result = eng.run(entry)
    assert result.status == ExecutionStatus.REJECTED


def test_run_expired_returns_expired():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("print('x')"), status=ApprovalStatus.EXPIRED)
    result = eng.run(entry)
    assert result.status == ExecutionStatus.EXPIRED


# ── allowlist check ───────────────────────────────────────────────────────────

def test_approved_but_not_in_allowlist_blocked():
    eng = ExecutionEngine(allowlist=["only_this"])
    entry = _entry(_py_action("print('x')"))
    result = eng.run(entry)
    assert result.status == ExecutionStatus.BLOCKED
    assert "allowlist" in (result.error or "")


def test_empty_allowlist_blocks_everything():
    eng = ExecutionEngine(allowlist=[])
    entry = _entry(_py_action("print('x')"))
    result = eng.run(entry)
    assert result.status == ExecutionStatus.BLOCKED


# ── successful execution ─────────────────────────────────────────────────────

def test_allowed_command_returns_success():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("print('hello')"))
    result = eng.run(entry)
    assert result.status == ExecutionStatus.SUCCESS


def test_success_result_has_stdout():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("print('hello-world')"))
    result = eng.run(entry)
    assert result.stdout is not None
    assert "hello-world" in result.stdout


def test_success_returncode_zero():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("print('x')"))
    result = eng.run(entry)
    assert result.returncode == 0


def test_duration_ms_positive():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("print('x')"))
    result = eng.run(entry)
    assert result.duration_ms > 0


def test_success_appends_to_history():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("print('x')"))
    eng.run(entry)
    assert len(eng._history) == 1


# ── failed execution ──────────────────────────────────────────────────────────

def test_nonzero_exit_returns_failed():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("import sys; sys.exit(2)"))
    result = eng.run(entry)
    assert result.status == ExecutionStatus.FAILED
    assert result.returncode == 2


# ── journal integration ──────────────────────────────────────────────────────

def test_success_records_to_journal():
    journal = DecisionJournal()
    eng = ExecutionEngine(allowlist=[PYBIN], decision_journal=journal)
    entry = _entry(_py_action("print('x')"))
    eng.run(entry)
    entries = journal.get_entries()
    assert len(entries) == 1
    assert entries[0].decision_type == "executed"
    assert entries[0].outcome == "success"


# ── blocked-no-history ───────────────────────────────────────────────────────

def test_blocked_does_not_record_to_history():
    eng = ExecutionEngine(allowlist=[PYBIN])
    entry = _entry(_py_action("print('x')"), status=ApprovalStatus.PENDING)
    eng.run(entry)
    assert len(eng._history) == 0


# ── history ───────────────────────────────────────────────────────────────────

def test_history_respects_limit():
    eng = ExecutionEngine(allowlist=[PYBIN])
    for _ in range(5):
        eng.run(_entry(_py_action("print('x')")))
    assert len(eng.history(limit=3)) == 3


def test_history_empty_initially():
    eng = ExecutionEngine(allowlist=[PYBIN])
    assert eng.history() == []


# ── thread safety ────────────────────────────────────────────────────────────

def test_thread_safety_concurrent_runs():
    eng = ExecutionEngine(allowlist=[PYBIN])
    errors: list[Exception] = []

    def worker():
        try:
            eng.run(_entry(_py_action("print('x')")))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(eng._history) == 10


# ── status last_status ────────────────────────────────────────────────────────

def test_status_last_status_reflects_most_recent():
    eng = ExecutionEngine(allowlist=[PYBIN])
    eng.run(_entry(_py_action("print('a')")))
    eng.run(_entry(_py_action("import sys; sys.exit(1)")))
    assert eng.status()["last_status"] == "failed"
