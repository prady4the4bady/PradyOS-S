"""AdmissionVerdict — structured output of the Proving Ground pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


@dataclass
class TestRun:
    """Result of running a test suite command."""
    command: str
    exit_code: int | None
    stdout_tail: str
    stderr_tail: str
    timed_out: bool
    duration_sec: float

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout_tail": self.stdout_tail[-2000:],
            "stderr_tail": self.stderr_tail[-2000:],
            "timed_out": self.timed_out,
            "duration_sec": self.duration_sec,
            "passed": self.passed,
        }


@dataclass
class ConstitutionScan:
    """Result of scanning source files for constitutional violations."""
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    scanned_files: int = 0

    @property
    def clean(self) -> bool:
        return len(self.violations) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "violations": self.violations,
            "warnings": self.warnings,
            "scanned_files": self.scanned_files,
            "clean": self.clean,
        }


@dataclass
class DependencyAudit:
    """Result of scanning declared dependencies."""
    flagged: list[dict[str, Any]] = field(default_factory=list)
    total_deps: int = 0
    manager: str = "unknown"

    @property
    def safe(self) -> bool:
        return len(self.flagged) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "manager": self.manager,
            "total_deps": self.total_deps,
            "flagged": self.flagged,
            "safe": self.safe,
        }


@dataclass
class AdmissionVerdict:
    """Final verdict produced by the Proving Ground pipeline."""

    repo_url: str
    repo_ref: str                    # branch / tag / commit
    workspace: str                   # temp dir used
    status: AdmissionStatus = AdmissionStatus.PENDING
    test_run: TestRun | None = None
    constitution_scan: ConstitutionScan | None = None
    dependency_audit: DependencyAudit | None = None
    reason: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    correlation_id: str | None = None

    @property
    def duration_sec(self) -> float:
        if self.finished_at is None:
            return time.time() - self.started_at
        return self.finished_at - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_url": self.repo_url,
            "repo_ref": self.repo_ref,
            "workspace": self.workspace,
            "status": self.status.value,
            "test_run": self.test_run.to_dict() if self.test_run else None,
            "constitution_scan": self.constitution_scan.to_dict() if self.constitution_scan else None,
            "dependency_audit": self.dependency_audit.to_dict() if self.dependency_audit else None,
            "reason": self.reason,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_sec": self.duration_sec,
            "correlation_id": self.correlation_id,
        }
