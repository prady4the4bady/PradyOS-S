"""AURORA THRONE tests — render shape, embedded Imperium wiring, hidden-CLI doctrine."""

from __future__ import annotations

from rich.console import Console

from pradyos.aurora_throne.app import Throne
from pradyos.aurora_throne.widgets import (
    approvals_panel,
    audit_panel,
    health_panel,
    incidents_panel,
    queue_panel,
)
from pradyos.core.types import TaskState
from pradyos.imperium.checkpoint import CheckpointStore
from pradyos.imperium.kernel import Imperium
from pradyos.imperium.task import ImperiumTask


def test_widgets_render_without_data():
    Console().print(health_panel(None))
    Console().print(approvals_panel([]))
    Console().print(incidents_panel([]))
    Console().print(audit_panel([]))
    Console().print(queue_panel({"total": 0}, []))


def test_widgets_render_with_data():
    snap = {
        "cpu_percent": 12.3, "ram_percent": 55.5, "swap_percent": 0,
        "disk": [{"mount": "/", "percent": 70, "device": "/dev/sda1",
                  "total_mb": 1024, "used_mb": 100, "fstype": "ext4"}],
        "gpus": [],
        "hostname": "test-host", "platform": "linux", "uptime_sec": 12345,
        "process_count": 42, "load_average": [0.1, 0.2, 0.3],
    }
    Console().print(health_panel(snap))
    Console().print(queue_panel({"total": 3, "state.QUEUED": 1, "state.RUNNING": 1},
                                 [{"task_id": "tk_x", "state": "RUNNING",
                                   "kind": "titan.shell", "intent": "ls",
                                   "priority": "OPERATIONAL"}]))
    Console().print(approvals_panel([{"task_id": "tk_y", "kind": "project_proposal",
                                       "intent": "new init",
                                       "escalation_rule": "new_project_proposal",
                                       "escalation_reason": "needs approval"}]))
    Console().print(incidents_panel([{"severity": "CRIT", "component": "cpu",
                                       "summary": "cpu 99%", "occurrences": 5}]))
    Console().print(audit_panel([{"timestamp_iso": "2026-05-22T00:00:00Z",
                                   "agent_id": "titan_ops", "kind": "command",
                                   "exit_code": 0, "summary": "ran ls"}]))


def test_throne_once_renders(isolated_audit, isolated_bus, tmp_state):
    """The Throne should render exactly once and exit without launching a shell."""
    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))
    kern.submit(ImperiumTask(kind="project_proposal", intent="Phase 1 build"))
    kern.run_one()  # escalates
    throne = Throne(imperium=kern, audit=isolated_audit, refresh_hz=10)
    throne.run(once=True)  # should not raise


def test_throne_approval_path(isolated_audit, isolated_bus, tmp_state):
    kern = Imperium(audit=isolated_audit, bus=isolated_bus,
                    checkpoint=CheckpointStore(state_dir=tmp_state))

    kern.register_handler("noop", lambda t: {"ok": True})
    rec = kern.submit(ImperiumTask(kind="project_proposal", intent="Phase 1"))
    kern.run_one()
    assert rec.state is TaskState.ESCALATED
    throne = Throne(imperium=kern, audit=isolated_audit)
    assert throne.approve(rec.spec.task_id) is True


def test_throne_hidden_cli_doctrine(isolated_audit, tmp_state):
    """The Throne does NOT expose a shell. The class has no exec_shell-style
    method. This guards the hidden-CLI doctrine at the test level."""
    throne = Throne(imperium=None, audit=isolated_audit)
    forbidden = {"exec", "shell", "system", "run_shell", "command"}
    public = {m for m in dir(throne) if not m.startswith("_")}
    for f in forbidden:
        assert f not in public, f"Throne must not expose {f!r}"
