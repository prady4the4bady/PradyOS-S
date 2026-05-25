"""test_sovereign_cli.py -- SOVEREIGN CLI tests (Phase 3).

Tests the headless pradyos-sovereign command interface:
  - status (reads checkpoint)
  - approve / reject (writes decisions file)
  - list-campaigns
  - schedule list / add / remove

All tests use isolated temporary directories so they never touch
the live var/state directory.  Windows-safe: no subprocess signals,
no fork, no AF_UNIX.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_checkpoint(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _read_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# CLI import helpers
# ---------------------------------------------------------------------------

def _make_cli(tmp_path: Path):
    """Return the cli module patched to use tmp_path for state."""
    import importlib
    import sys

    # Patch env so cli uses our tmp dir
    import os
    os.environ["PRADYOS_STATE_PATH"] = str(tmp_path)

    # Force reload to pick up new env
    if "pradyos.sovereign.cli" in sys.modules:
        del sys.modules["pradyos.sovereign.cli"]

    from pradyos.sovereign import cli
    # Override module-level path constants
    cli._STATE_DIR  = tmp_path
    cli._CHECKPOINT = tmp_path / "imperium_tasks.jsonl"
    cli._DECISIONS  = tmp_path / "sovereign_decisions.jsonl"
    cli._SCHEDULES  = tmp_path / "schedules.jsonl"
    return cli


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_no_checkpoint(self, tmp_path: Path, capsys):
        cli = _make_cli(tmp_path)
        rc = cli.cmd_status(cli.build_parser().parse_args(["status"]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "SOVEREIGN STATUS" in out
        assert "No task history" in out

    def test_status_with_tasks(self, tmp_path: Path, capsys):
        cp = tmp_path / "imperium_tasks.jsonl"
        _write_checkpoint(cp, [
            {"task_id": "tk-aaa", "state": "SUCCEEDED", "kind": "research",
             "intent": "do research", "escalation_reason": None},
            {"task_id": "tk-bbb", "state": "ESCALATED", "kind": "research",
             "intent": "delete prod db",
             "escalation_reason": "too dangerous"},
        ])
        cli = _make_cli(tmp_path)
        rc = cli.cmd_status(cli.build_parser().parse_args(["status"]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "SUCCEEDED" in out
        assert "ESCALATED" in out
        assert "PENDING APPROVALS" in out
        assert "tk-bbb"[:8] in out or "delete prod db" in out

    def test_status_warden_offline(self, tmp_path: Path, capsys):
        cli = _make_cli(tmp_path)
        # Warden is not running — status should still return 0
        rc = cli.cmd_status(cli.build_parser().parse_args(["status"]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "offline" in out.lower() or "WARDEN" in out


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------

class TestApprove:
    def test_approve_writes_decision(self, tmp_path: Path, capsys):
        cp = tmp_path / "imperium_tasks.jsonl"
        _write_checkpoint(cp, [
            {"task_id": "tk-abc123", "state": "ESCALATED",
             "kind": "research", "intent": "some research",
             "escalation_reason": "risky"},
        ])
        cli = _make_cli(tmp_path)
        rc = cli.cmd_approve(
            cli.build_parser().parse_args(["approve", "tk-abc123"])
        )
        assert rc == 0
        decisions = _read_decisions(tmp_path / "sovereign_decisions.jsonl")
        assert len(decisions) == 1
        assert decisions[0]["action"] == "approve"
        assert decisions[0]["task_id"] == "tk-abc123"
        assert decisions[0]["approver"] == "sovereign"

    def test_approve_prefix_match(self, tmp_path: Path, capsys):
        cp = tmp_path / "imperium_tasks.jsonl"
        _write_checkpoint(cp, [
            {"task_id": "tk-unique-xyz99", "state": "ESCALATED",
             "kind": "research", "intent": "task", "escalation_reason": "x"},
        ])
        cli = _make_cli(tmp_path)
        rc = cli.cmd_approve(
            cli.build_parser().parse_args(["approve", "tk-unique"])
        )
        assert rc == 0
        dec = _read_decisions(tmp_path / "sovereign_decisions.jsonl")
        assert dec[0]["task_id"] == "tk-unique-xyz99"

    def test_approve_not_found(self, tmp_path: Path, capsys):
        _write_checkpoint(tmp_path / "imperium_tasks.jsonl", [])
        cli = _make_cli(tmp_path)
        rc = cli.cmd_approve(
            cli.build_parser().parse_args(["approve", "nonexistent"])
        )
        assert rc != 0

    def test_approve_custom_approver(self, tmp_path: Path, capsys):
        cp = tmp_path / "imperium_tasks.jsonl"
        _write_checkpoint(cp, [
            {"task_id": "tk-ZZZ", "state": "ESCALATED",
             "kind": "research", "intent": "i", "escalation_reason": "x"},
        ])
        cli = _make_cli(tmp_path)
        rc = cli.cmd_approve(
            cli.build_parser().parse_args(["approve", "tk-ZZZ", "--approver", "admin"])
        )
        assert rc == 0
        dec = _read_decisions(tmp_path / "sovereign_decisions.jsonl")
        assert dec[0]["approver"] == "admin"


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------

class TestReject:
    def test_reject_writes_decision(self, tmp_path: Path, capsys):
        cp = tmp_path / "imperium_tasks.jsonl"
        _write_checkpoint(cp, [
            {"task_id": "tk-R1", "state": "ESCALATED",
             "kind": "research", "intent": "x", "escalation_reason": "y"},
        ])
        cli = _make_cli(tmp_path)
        rc = cli.cmd_reject(
            cli.build_parser().parse_args(["reject", "tk-R1", "--reason", "too risky"])
        )
        assert rc == 0
        dec = _read_decisions(tmp_path / "sovereign_decisions.jsonl")
        assert dec[0]["action"] == "reject"
        assert dec[0]["reason"] == "too risky"
        assert dec[0]["task_id"] == "tk-R1"

    def test_reject_not_found(self, tmp_path: Path, capsys):
        _write_checkpoint(tmp_path / "imperium_tasks.jsonl", [])
        cli = _make_cli(tmp_path)
        rc = cli.cmd_reject(cli.build_parser().parse_args(["reject", "no-such-task"]))
        assert rc != 0


# ---------------------------------------------------------------------------
# list-campaigns
# ---------------------------------------------------------------------------

class TestListCampaigns:
    def test_list_empty(self, tmp_path: Path, capsys, monkeypatch):
        cli = _make_cli(tmp_path)
        # Monkeypatch the registry to return an empty list
        from pradyos.campaign import registry as reg_mod
        from pradyos.campaign.registry import CampaignRegistry

        class _FakeReg:
            def all(self):
                return []

        monkeypatch.setattr(reg_mod, "CampaignRegistry", lambda **kw: _FakeReg())
        rc = cli.cmd_list_campaigns(
            cli.build_parser().parse_args(["list-campaigns"])
        )
        assert rc == 0
        assert "No campaigns" in capsys.readouterr().out

    def test_list_with_campaigns(self, tmp_path: Path, capsys, monkeypatch):
        from pradyos.campaign.model import Campaign, CampaignStatus
        from pradyos.campaign import registry as reg_mod
        from pradyos.core.ids import new_id

        c = Campaign(name="Test Campaign", intent="test", submitted_by="test")
        c.status = CampaignStatus.SUCCEEDED

        class _FakeReg:
            def all(self):
                return [c]

        monkeypatch.setattr(reg_mod, "CampaignRegistry", lambda **kw: _FakeReg())
        cli = _make_cli(tmp_path)
        rc = cli.cmd_list_campaigns(
            cli.build_parser().parse_args(["list-campaigns"])
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "Test Campaign" in out
        assert "succeeded" in out


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------

class TestScheduleCLI:
    def test_schedule_add_and_list(self, tmp_path: Path, capsys):
        cli = _make_cli(tmp_path)
        parser = cli.build_parser()

        # Patch scheduler to use tmp_path
        import pradyos.campaign.scheduler as sched_mod
        orig = sched_mod.CampaignScheduler

        def _patched(**kw):
            return orig(state_dir=tmp_path)

        # Directly call add with our scheduler
        from pradyos.campaign.scheduler import CampaignScheduler
        sched = CampaignScheduler(state_dir=tmp_path)
        sid = sched.add_schedule(
            name="Nightly Backup",
            cron="0 2 * * *",
            intent="back up database",
        )

        # List via scheduler
        schedules = sched.list_schedules()
        assert len(schedules) == 1
        assert schedules[0]["name"] == "Nightly Backup"
        assert schedules[0]["schedule_id"] == sid

    def test_schedule_remove(self, tmp_path: Path):
        from pradyos.campaign.scheduler import CampaignScheduler
        sched = CampaignScheduler(state_dir=tmp_path)
        sid = sched.add_schedule("My Sched", "0 6 * * *", "daily task")
        assert len(sched.list_schedules()) == 1

        ok = sched.remove_schedule(sid)
        assert ok is True
        assert len(sched.list_schedules()) == 0

    def test_schedule_remove_prefix(self, tmp_path: Path):
        from pradyos.campaign.scheduler import CampaignScheduler
        sched = CampaignScheduler(state_dir=tmp_path)
        sid = sched.add_schedule("Sched-A", "0 9 * * 1", "monday task")
        prefix = sid[:6]
        ok = sched.remove_schedule(prefix)
        assert ok is True
        assert sched.list_schedules() == []

    def test_schedule_cmd_list_empty(self, tmp_path: Path, capsys):
        cli = _make_cli(tmp_path)
        args = cli.build_parser().parse_args(["schedule", "list"])
        rc = cli.cmd_schedule(args)
        assert rc == 0
        assert "No schedules" in capsys.readouterr().out

    def test_schedule_cmd_add(self, tmp_path: Path, capsys):
        from pradyos.campaign import scheduler as sched_mod
        orig = sched_mod.CampaignScheduler

        # Patch to use tmp_path
        sched_mod.CampaignScheduler = lambda **kw: orig(state_dir=tmp_path)
        try:
            cli = _make_cli(tmp_path)
            args = cli.build_parser().parse_args([
                "schedule", "add",
                "--name", "Weekly", "--cron", "0 6 * * 1",
                "--intent", "weekly maintenance",
            ])
            rc = cli.cmd_schedule(args)
            assert rc == 0
            out = capsys.readouterr().out
            assert "Schedule added" in out
            assert "Weekly" in out
        finally:
            sched_mod.CampaignScheduler = orig


# ---------------------------------------------------------------------------
# Parser smoke test
# ---------------------------------------------------------------------------

class TestParser:
    def test_parser_help(self):
        from pradyos.sovereign.cli import build_parser
        p = build_parser()
        assert p is not None

    def test_subcommands_present(self):
        from pradyos.sovereign.cli import build_parser
        p = build_parser()
        # Parse each valid subcommand just to check they don't raise
        for cmd in ["status"]:
            args = p.parse_args([cmd])
            assert args.command == cmd

    def test_approve_args(self):
        from pradyos.sovereign.cli import build_parser
        p = build_parser()
        args = p.parse_args(["approve", "task-123", "--approver", "admin"])
        assert args.task_id == "task-123"
        assert args.approver == "admin"

    def test_reject_args(self):
        from pradyos.sovereign.cli import build_parser
        p = build_parser()
        args = p.parse_args(["reject", "task-456", "--reason", "nope"])
        assert args.task_id == "task-456"
        assert args.reason == "nope"

    def test_schedule_add_args(self):
        from pradyos.sovereign.cli import build_parser
        p = build_parser()
        args = p.parse_args([
            "schedule", "add",
            "--name", "N", "--cron", "0 * * * *", "--intent", "hourly",
        ])
        assert args.name == "N"
        assert args.cron == "0 * * * *"

    def test_list_campaigns_status_filter(self):
        from pradyos.sovereign.cli import build_parser
        p = build_parser()
        args = p.parse_args(["list-campaigns", "--status", "running"])
        assert args.status == "running"
