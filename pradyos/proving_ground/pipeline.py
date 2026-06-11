"""Proving Ground admission pipeline.

Orchestrates the full clone → scan → test → verdict flow.

Usage (direct)::

    pipeline = AdmissionPipeline()
    verdict = pipeline.admit("https://github.com/example/myrepo", ref="main")
    print(verdict.status, verdict.reason)

Usage (via IMPERIUM — submit as a task)::

    kern.submit(ImperiumTask(
        kind="proving_ground.admit",
        intent="admit myrepo",
        payload={"repo_url": "https://github.com/example/myrepo", "ref": "main"},
    ))

The IMPERIUM handler is registered automatically when the pipeline is wired
into the kernel via ``AdmissionPipeline.register_with(imperium)``.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.core.bus import EventBus, get_bus
from pradyos.core.ids import new_id
from pradyos.proving_ground.scanner import scan_dependencies, scan_directory
from pradyos.proving_ground.verdict import (
    AdmissionStatus,
    AdmissionVerdict,
    ConstitutionScan,
    DependencyAudit,
    TestRun,
)

log = logging.getLogger("pradyos.proving_ground")

# Maximum time (seconds) to allow the repo's test suite to run
DEFAULT_TEST_TIMEOUT = int(os.environ.get("PRADYOS_PG_TEST_TIMEOUT", "120"))

# Candidate test commands — tried in order; first found is used
_TEST_COMMANDS: list[list[str]] = [
    [sys.executable, "-m", "pytest", "--tb=short", "-q"],
    [sys.executable, "-m", "unittest", "discover", "-q"],
    [sys.executable, "setup.py", "test"],
]


def _detect_test_command(workspace: str) -> list[str] | None:
    """Return the first applicable test command for the workspace."""
    root = Path(workspace)
    # Check pytest availability and presence of tests/
    if (root / "tests").is_dir() or list(root.glob("test_*.py")) or list(root.glob("*_test.py")):
        return [sys.executable, "-m", "pytest", "--tb=short", "-q", "--no-header"]
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists():
        return [sys.executable, "-m", "pytest", "--tb=short", "-q", "--no-header"]
    # npm
    if (root / "package.json").exists():
        npm = shutil.which("npm")
        if npm:
            return [npm, "test", "--", "--passWithNoTests"]
    return None


class AdmissionPipeline:
    """Full-stack repo admission orchestrator."""

    AGENT_ID = "proving_ground"

    def __init__(
        self,
        audit: AuditLog | None = None,
        bus: EventBus | None = None,
        test_timeout: int = DEFAULT_TEST_TIMEOUT,
    ) -> None:
        self.audit = audit or get_audit_log()
        self.bus = bus or get_bus()
        self.test_timeout = test_timeout
        self._verdicts: dict[str, AdmissionVerdict] = {}

    # ---------- public API ----------

    def admit(
        self,
        repo_url: str,
        ref: str = "main",
        correlation_id: str | None = None,
    ) -> AdmissionVerdict:
        """Clone, scan, and test a repository. Returns an AdmissionVerdict."""
        cid = correlation_id or new_id("pg")
        workspace = tempfile.mkdtemp(prefix="pradyos-pg-")
        verdict = AdmissionVerdict(
            repo_url=repo_url,
            repo_ref=ref,
            workspace=workspace,
            correlation_id=cid,
        )
        log.info("Proving Ground: admitting %s@%s → %s", repo_url, ref, workspace)
        self.audit.record(
            agent_id=self.AGENT_ID,
            kind="admission",
            summary=f"ADMIT START: {repo_url}@{ref}",
            detail={"repo_url": repo_url, "ref": ref, "workspace": workspace},
            correlation_id=cid,
        )

        try:
            self._clone(repo_url, ref, workspace, verdict)
            if verdict.status is AdmissionStatus.REJECTED:
                return self._finish(verdict)

            self._constitution_scan(workspace, verdict)
            if verdict.status is AdmissionStatus.REJECTED:
                return self._finish(verdict)

            self._dependency_audit(workspace, verdict)

            self._run_tests(workspace, verdict)

            # Final status: promote to ADMITTED if nothing blocked
            if verdict.status is AdmissionStatus.PENDING:
                verdict.status = AdmissionStatus.ADMITTED
                verdict.reason = "all checks passed"

        except Exception as e:  # noqa: BLE001
            log.exception("Proving Ground pipeline error")
            verdict.status = AdmissionStatus.QUARANTINED
            verdict.reason = f"pipeline error: {e}"
        finally:
            # Clean up workspace
            try:
                shutil.rmtree(workspace, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass

        return self._finish(verdict)

    def last_verdict(self, correlation_id: str) -> AdmissionVerdict | None:
        return self._verdicts.get(correlation_id)

    def register_with(self, imperium: Any) -> None:
        """Register the admission handler into IMPERIUM's task dispatch."""

        def _handler(task: Any) -> dict[str, Any]:
            url = task.payload.get("repo_url", "")
            ref = task.payload.get("ref", "main")
            if not url:
                return {"ok": False, "error": "proving_ground.admit requires payload.repo_url"}
            verdict = self.admit(url, ref=ref, correlation_id=task.task_id)
            return {
                "ok": verdict.status is AdmissionStatus.ADMITTED,
                "verdict": verdict.to_dict(),
                "error": verdict.reason if verdict.status is not AdmissionStatus.ADMITTED else None,
            }

        imperium.register_handler("proving_ground.admit", _handler)
        log.info("Proving Ground handler registered with IMPERIUM")

    # ---------- pipeline stages ----------

    def _clone(self, repo_url: str, ref: str, workspace: str, verdict: AdmissionVerdict) -> None:
        """Clone the repository at the given ref into workspace."""
        git = shutil.which("git")
        if not git:
            verdict.status = AdmissionStatus.QUARANTINED
            verdict.reason = "git not available on this host"
            return

        cmd = [git, "clone", "--depth=1", "--branch", ref, repo_url, workspace]
        try:
            result = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                verdict.status = AdmissionStatus.REJECTED
                verdict.reason = (
                    f"git clone failed (exit {result.returncode}): {result.stderr[:500]}"
                )
        except subprocess.TimeoutExpired:
            verdict.status = AdmissionStatus.QUARANTINED
            verdict.reason = "git clone timed out after 60s"
        except OSError as e:
            verdict.status = AdmissionStatus.QUARANTINED
            verdict.reason = f"clone OS error: {e}"

    def _constitution_scan(self, workspace: str, verdict: AdmissionVerdict) -> None:
        scan: ConstitutionScan = scan_directory(workspace)
        verdict.constitution_scan = scan
        hard = [v for v in scan.violations if v.get("severity") == "HARD"]
        soft = [v for v in scan.violations if v.get("severity") == "SOFT"]
        if hard:
            verdict.status = AdmissionStatus.REJECTED
            verdict.reason = (
                f"constitutional HARD violation: {hard[0]['label']} in {hard[0]['file']}"
            )
        elif soft:
            verdict.status = AdmissionStatus.QUARANTINED
            verdict.reason = f"constitutional SOFT violation: {soft[0]['label']}"

    def _dependency_audit(self, workspace: str, verdict: AdmissionVerdict) -> None:
        manager, total, flagged = scan_dependencies(workspace)
        audit = DependencyAudit(manager=manager, total_deps=total, flagged=flagged)
        verdict.dependency_audit = audit
        if flagged:
            verdict.status = AdmissionStatus.QUARANTINED
            verdict.reason = (
                f"dependency audit: flagged {flagged[0]['package']} — {flagged[0]['reason']}"
            )

    def _run_tests(self, workspace: str, verdict: AdmissionVerdict) -> None:
        cmd = _detect_test_command(workspace)
        if cmd is None:
            verdict.test_run = TestRun(
                command="(no test suite detected)",
                exit_code=0,
                stdout_tail="No tests found — treating as passed",
                stderr_tail="",
                timed_out=False,
                duration_sec=0.0,
            )
            return

        started = time.time()
        timed_out = False
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=self.test_timeout,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = None
            stdout = ""
            stderr = f"test suite timed out after {self.test_timeout}s"
        except OSError as e:
            exit_code = -1
            stdout = ""
            stderr = str(e)
        duration = time.time() - started

        run = TestRun(
            command=" ".join(cmd),
            exit_code=exit_code,
            stdout_tail=(stdout or "")[-3000:],
            stderr_tail=(stderr or "")[-1000:],
            timed_out=timed_out,
            duration_sec=duration,
        )
        verdict.test_run = run

        if not run.passed and verdict.status is AdmissionStatus.PENDING:
            verdict.status = AdmissionStatus.QUARANTINED
            verdict.reason = (
                f"test suite failed (exit {exit_code})"
                if not timed_out
                else f"test suite timed out after {self.test_timeout}s"
            )

    # ---------- finish ----------

    def _finish(self, verdict: AdmissionVerdict) -> AdmissionVerdict:
        verdict.finished_at = time.time()
        self._verdicts[verdict.correlation_id or ""] = verdict
        self.audit.record(
            agent_id=self.AGENT_ID,
            kind="admission",
            summary=f"ADMIT {verdict.status.value}: {verdict.repo_url}",
            detail=verdict.to_dict(),
            correlation_id=verdict.correlation_id,
        )
        self.bus.publish("proving_ground.verdict", verdict.to_dict())
        log.info(
            "Proving Ground verdict: %s — %s (%.1fs)",
            verdict.status.value,
            verdict.reason,
            verdict.duration_sec,
        )
        return verdict

    # ---------- inline admission (no file I/O, no network) ----------

    # Hard violations → REJECTED immediately
    _INLINE_HARD = [
        re.compile(r"rm\s+-[rRfF]{1,4}\s*/", re.I),  # rm -rf /
        re.compile(r"\bDROP\s+TABLE\b", re.I),  # SQL DROP TABLE
        re.compile(r"\bformat\s+[a-zA-Z]:", re.I),  # format c:
        re.compile(r"\bmkfs\.", re.I),  # mkfs.ext4 etc.
        re.compile(r"dd\s+if=/dev/zero", re.I),  # disk wipe
        re.compile(r":\(\)\s*\{", re.I),  # fork bomb
    ]

    # Soft violations → QUARANTINED
    _INLINE_SOFT = [
        re.compile(r"\beval\s*\(", re.I),  # eval()
        re.compile(r"\bexec\s*\(", re.I),  # exec()
        re.compile(r"__import__\s*\("),  # __import__()
        re.compile(r"\brmdir\s+/", re.I),  # rmdir /
        re.compile(r"(?i)(password|secret|token)\s*=\s*['\"][^'\"]{4,}['\"]"),
    ]

    def admit_inline(self, intent: str, kind: str) -> AdmissionVerdict:
        """Scan an inline task intent string for constitutional violations.

        Runs only the constitutional scan phase — no file I/O, no network,
        no cloning.  Returns an :class:`AdmissionVerdict` immediately.

        Severity:
            HARD → REJECTED
            SOFT → QUARANTINED
            none → ADMITTED
        """

        for pattern in self._INLINE_HARD:
            if pattern.search(intent):
                return AdmissionVerdict(
                    repo_url=f"inline://{kind}/{intent[:40]}",
                    repo_ref="inline",
                    workspace="",
                    status=AdmissionStatus.REJECTED,
                    reason=f"hard constitutional violation detected in intent: {pattern.pattern!r}",
                )

        for pattern in self._INLINE_SOFT:
            if pattern.search(intent):
                return AdmissionVerdict(
                    repo_url=f"inline://{kind}/{intent[:40]}",
                    repo_ref="inline",
                    workspace="",
                    status=AdmissionStatus.QUARANTINED,
                    reason=f"soft constitutional violation detected in intent: {pattern.pattern!r}",
                )

        return AdmissionVerdict(
            repo_url=f"inline://{kind}/{intent[:40]}",
            repo_ref="inline",
            workspace="",
            status=AdmissionStatus.ADMITTED,
            reason="inline task passed constitutional scan",
        )
