from __future__ import annotations

import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pradyos.core.approval_queue import ApprovalEntry, ApprovalQueue
    from pradyos.core.decision_journal import DecisionJournal


class ExecutionStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ExecutionResult:
    entry_id: str
    action: str
    status: ExecutionStatus
    stdout: str | None
    stderr: str | None
    returncode: int | None
    executed_at: float
    duration_ms: float
    error: str | None

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "action": self.action,
            "status": self.status.value,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "executed_at": self.executed_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class ExecutionEngine:
    def __init__(
        self,
        allowlist: list[str] | None = None,
        approval_queue: "ApprovalQueue | None" = None,
        decision_journal: "DecisionJournal | None" = None,
        timeout: float = 30.0,
    ) -> None:
        self._allowlist: set[str] = set(allowlist or [])
        self._queue = approval_queue
        self._journal = decision_journal
        self._timeout = timeout
        self._history: list[ExecutionResult] = []
        self._lock = threading.Lock()

    def run(self, entry, timeout: float | None = None) -> ExecutionResult:
        from pradyos.core.approval_queue import ApprovalStatus

        executed_at = time.time()

        # ── Hard rule 1: status check ────────────────────────────────────────
        if entry.status == ApprovalStatus.REJECTED:
            return ExecutionResult(
                entry_id=entry.id, action=entry.action,
                status=ExecutionStatus.REJECTED,
                stdout=None, stderr=None, returncode=None,
                executed_at=executed_at, duration_ms=0.0,
                error="Action was rejected",
            )
        if entry.status == ApprovalStatus.EXPIRED:
            return ExecutionResult(
                entry_id=entry.id, action=entry.action,
                status=ExecutionStatus.EXPIRED,
                stdout=None, stderr=None, returncode=None,
                executed_at=executed_at, duration_ms=0.0,
                error="Action expired before execution",
            )
        if entry.status != ApprovalStatus.APPROVED:
            return ExecutionResult(
                entry_id=entry.id, action=entry.action,
                status=ExecutionStatus.BLOCKED,
                stdout=None, stderr=None, returncode=None,
                executed_at=executed_at, duration_ms=0.0,
                error="Action not approved",
            )

        # ── Hard rule 2: allowlist check ─────────────────────────────────────
        try:
            cmd = shlex.split(entry.action)
        except ValueError as exc:
            return ExecutionResult(
                entry_id=entry.id, action=entry.action,
                status=ExecutionStatus.BLOCKED,
                stdout=None, stderr=None, returncode=None,
                executed_at=executed_at, duration_ms=0.0,
                error=f"Could not parse command: {exc}",
            )
        if not cmd:
            return ExecutionResult(
                entry_id=entry.id, action=entry.action,
                status=ExecutionStatus.BLOCKED,
                stdout=None, stderr=None, returncode=None,
                executed_at=executed_at, duration_ms=0.0,
                error="Empty command",
            )
        base = cmd[0]
        if base not in self._allowlist:
            return ExecutionResult(
                entry_id=entry.id, action=entry.action,
                status=ExecutionStatus.BLOCKED,
                stdout=None, stderr=None, returncode=None,
                executed_at=executed_at, duration_ms=0.0,
                error="Command not in allowlist",
            )

        # ── Execute ──────────────────────────────────────────────────────────
        effective_timeout = timeout if timeout is not None else self._timeout
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            duration_ms = (time.perf_counter() - t0) * 1000
            status = (
                ExecutionStatus.SUCCESS if proc.returncode == 0
                else ExecutionStatus.FAILED
            )
            result = ExecutionResult(
                entry_id=entry.id, action=entry.action,
                status=status,
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
                executed_at=executed_at,
                duration_ms=duration_ms,
                error=None,
            )
        except subprocess.TimeoutExpired as exc:
            result = ExecutionResult(
                entry_id=entry.id, action=entry.action,
                status=ExecutionStatus.FAILED,
                stdout=None, stderr=None, returncode=None,
                executed_at=executed_at,
                duration_ms=(time.perf_counter() - t0) * 1000,
                error=f"Timeout after {exc.timeout}s",
            )
        except Exception as exc:
            result = ExecutionResult(
                entry_id=entry.id, action=entry.action,
                status=ExecutionStatus.FAILED,
                stdout=None, stderr=None, returncode=None,
                executed_at=executed_at,
                duration_ms=(time.perf_counter() - t0) * 1000,
                error=str(exc),
            )

        # ── Record to history + journal ──────────────────────────────────────
        with self._lock:
            self._history.append(result)

        if self._journal is not None:
            try:
                self._journal.record(
                    agent_id="execution_engine",
                    decision_type="executed",
                    rationale=f"action={entry.action} cmd={base}",
                    outcome=result.status.value,
                )
            except Exception:
                pass

        return result

    def history(self, limit: int = 100) -> list[ExecutionResult]:
        with self._lock:
            hist = list(self._history)
        return hist[-limit:]

    def status(self) -> dict:
        with self._lock:
            last = self._history[-1].status.value if self._history else None
            total = len(self._history)
        return {
            "allowlist": sorted(self._allowlist),
            "total_runs": total,
            "last_status": last,
        }
