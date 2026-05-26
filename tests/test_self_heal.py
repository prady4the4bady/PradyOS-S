"""Phase 11 — SelfHealEngine tests.

22 tests covering:
    1.  heal() returns a correct HealResult
    2.  quarantine is persisted to var/state/quarantine.json
    3.  is_quarantined() returns True after heal, False before
    4.  release_quarantine() removes from quarantine
    5.  bus event published on heal (isolated_bus fixture)
    6.  audit entry written on heal
    7.  kernel integration: task that exhausts retries triggers heal
    8.  quarantine_list() returns all quarantined task IDs
    9.  heal on unknown task_id raises TaskNotFound
    10. double-heal of same task is idempotent
    11. quarantine survives engine restart (persistence round-trip)
    12. release_quarantine on non-quarantined id is a no-op
    13. quarantine.json is valid JSON after heal
    14. HealResult.rolled_back_to is "none" when snapshot store is empty
    15. HealResult.rolled_back_to is snapshot ts when a snapshot exists
    16. heal() publishes correct payload fields
    17. multiple tasks can be quarantined independently
    18. release_quarantine removes only the specified task
    19. quarantine_list() is a copy (mutating it doesn't affect engine state)
    20. audit entry correlation_id matches task_id
    21. kernel integration: quarantine.json contains dead-lettered task_id
    22. kernel integration: warden bus event system.self_heal fired
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pradyos.core.audit import AuditLog
from pradyos.core.bus import EventBus
from pradyos.core.snapshot import SnapshotStore, SystemSnapshot
from pradyos.core.types import TaskState
from pradyos.imperium.exceptions import TaskNotFound
from pradyos.imperium.kernel import Imperium
from pradyos.imperium.self_heal import HealResult, SelfHealEngine
from pradyos.imperium.task import ImperiumTask


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

_SETTLE = 0.05  # seconds — in-process bus is synchronous; tiny settle is fine


def _make_engine(
    tmp_path: Path,
    monkeypatch,
    kernel=None,
    bus=None,
    snapshot_store=None,
    audit=None,
) -> SelfHealEngine:
    """Build a SelfHealEngine wired to tmp_path state dir."""
    monkeypatch.setenv("PRADYOS_STATE_PATH", str(tmp_path))

    if kernel is None:
        kernel = MagicMock()
        # rollback() is a no-op by default (task exists)
        kernel.rollback.return_value = None

    if bus is None:
        bus = EventBus()

    if snapshot_store is None:
        snapshot_store = SnapshotStore(path=tmp_path / "snapshots.jsonl")

    if audit is None:
        audit = AuditLog(path=tmp_path / "audit.jsonl")

    return SelfHealEngine(
        kernel=kernel,
        bus=bus,
        snapshot_store=snapshot_store,
        audit=audit,
    )


def _quarantine_path(tmp_path: Path) -> Path:
    return tmp_path / "quarantine.json"


def _submit_failing_task(kern: Imperium, max_retries: int = 0) -> str:
    """Register a handler that always fails and submit a task."""
    kern.register_handler("always_fail", lambda t: {"ok": False, "error": "boom"})
    t = ImperiumTask(
        kind="always_fail",
        intent="test fail task",
        max_retries=max_retries,
    )
    rec = kern.submit(t)
    return rec.spec.task_id


# ---------------------------------------------------------------------------
# Test 1: heal() returns correct HealResult
# ---------------------------------------------------------------------------

def test_heal_returns_correct_heal_result(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    result = engine.heal("task-abc", reason="retry_budget_exhausted")

    assert isinstance(result, HealResult)
    assert result.task_id == "task-abc"
    assert result.action_taken == "rollback_and_quarantine"
    assert result.quarantined is True


# ---------------------------------------------------------------------------
# Test 2: quarantine is persisted to quarantine.json
# ---------------------------------------------------------------------------

def test_quarantine_persisted_to_json(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    engine.heal("task-xyz")

    path = _quarantine_path(tmp_path)
    assert path.exists(), "quarantine.json must be written"
    data = json.loads(path.read_text())
    assert "task-xyz" in data["quarantine"]


# ---------------------------------------------------------------------------
# Test 3: is_quarantined() returns True after heal, False before
# ---------------------------------------------------------------------------

def test_is_quarantined_true_after_heal(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    assert not engine.is_quarantined("task-1")
    engine.heal("task-1")
    assert engine.is_quarantined("task-1")


# ---------------------------------------------------------------------------
# Test 4: release_quarantine() removes from quarantine
# ---------------------------------------------------------------------------

def test_release_quarantine_removes_task(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    engine.heal("task-2")
    assert engine.is_quarantined("task-2")

    engine.release_quarantine("task-2")
    assert not engine.is_quarantined("task-2")


# ---------------------------------------------------------------------------
# Test 5: bus event published on heal (isolated_bus)
# ---------------------------------------------------------------------------

def test_bus_event_published_on_heal(tmp_path, monkeypatch, isolated_bus):
    engine = _make_engine(tmp_path, monkeypatch, bus=isolated_bus)

    received: list[tuple[str, dict]] = []
    isolated_bus.subscribe("system.self_heal", lambda t, p: received.append((t, p)))

    engine.heal("task-bus", reason="retry_budget_exhausted")

    assert len(received) == 1
    topic, payload = received[0]
    assert topic == "system.self_heal"
    assert payload["task_id"] == "task-bus"
    assert payload["reason"] == "retry_budget_exhausted"


# ---------------------------------------------------------------------------
# Test 6: audit entry written on heal
# ---------------------------------------------------------------------------

def test_audit_entry_written_on_heal(tmp_path, monkeypatch):
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    engine = _make_engine(tmp_path, monkeypatch, audit=audit)
    engine.heal("task-audit")

    # tail() returns most recent entry first
    tail = audit.tail(10)
    summaries = [r.summary for r in tail]
    assert any("task-audit"[:8] in s for s in summaries), (
        f"expected audit entry for task-audit, got: {summaries}"
    )


# ---------------------------------------------------------------------------
# Test 7: kernel integration — exhausted retries triggers heal automatically
# ---------------------------------------------------------------------------

def test_kernel_integration_exhausted_retries_triggers_heal(tmp_path, monkeypatch):
    monkeypatch.setenv("PRADYOS_STATE_PATH", str(tmp_path))

    healed: list[str] = []

    kern = Imperium(
        audit=AuditLog(path=tmp_path / "audit.jsonl"),
        checkpoint=__import__(
            "pradyos.imperium.checkpoint", fromlist=["CheckpointStore"]
        ).CheckpointStore(state_dir=tmp_path),
    )

    snapshot_store = SnapshotStore(path=tmp_path / "snapshots.jsonl")
    bus = EventBus()
    audit = AuditLog(path=tmp_path / "audit2.jsonl")

    engine = SelfHealEngine(
        kernel=kern,
        bus=bus,
        snapshot_store=snapshot_store,
        audit=audit,
    )
    kern._self_heal_engine = engine

    task_id = _submit_failing_task(kern, max_retries=0)

    # Run one execution cycle — task fails, retries=0 → dead-letter → self-heal
    kern.run_one()

    assert engine.is_quarantined(task_id), (
        "task should be quarantined after retry budget exhausted"
    )


# ---------------------------------------------------------------------------
# Test 8: quarantine_list() returns all quarantined task IDs
# ---------------------------------------------------------------------------

def test_quarantine_list_returns_all_ids(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    engine.heal("task-a")
    engine.heal("task-b")
    engine.heal("task-c")

    ql = engine.quarantine_list()
    assert set(ql) == {"task-a", "task-b", "task-c"}


# ---------------------------------------------------------------------------
# Test 9: heal on unknown task_id raises TaskNotFound
# ---------------------------------------------------------------------------

def test_heal_unknown_task_id_raises_task_not_found(tmp_path, monkeypatch):
    # Kernel mock whose rollback raises TaskNotFound for unknown IDs
    kernel = MagicMock()
    kernel.rollback.side_effect = TaskNotFound("not found")

    engine = _make_engine(tmp_path, monkeypatch, kernel=kernel)
    with pytest.raises(TaskNotFound):
        engine.heal("nonexistent-task-id")


# ---------------------------------------------------------------------------
# Test 10: double-heal of same task is idempotent
# ---------------------------------------------------------------------------

def test_double_heal_is_idempotent(tmp_path, monkeypatch, isolated_bus):
    received: list[Any] = []
    isolated_bus.subscribe("system.self_heal", lambda t, p: received.append(p))

    engine = _make_engine(tmp_path, monkeypatch, bus=isolated_bus)
    engine.heal("task-dup")
    engine.heal("task-dup")

    # Still quarantined (set-add is idempotent)
    assert engine.is_quarantined("task-dup")
    # Quarantine list should have exactly one entry for task-dup
    assert engine.quarantine_list().count("task-dup") == 1
    # Bus event fires twice — that is intentional (full audit trail)
    assert len(received) == 2


# ---------------------------------------------------------------------------
# Test 11: quarantine survives engine restart (persistence round-trip)
# ---------------------------------------------------------------------------

def test_quarantine_survives_restart(tmp_path, monkeypatch):
    engine1 = _make_engine(tmp_path, monkeypatch)
    engine1.heal("persistent-task")
    assert engine1.is_quarantined("persistent-task")

    # Build a new engine instance pointing at the same state dir
    kernel2 = MagicMock()
    kernel2.rollback.return_value = None
    engine2 = SelfHealEngine(
        kernel=kernel2,
        bus=EventBus(),
        snapshot_store=SnapshotStore(path=tmp_path / "snapshots.jsonl"),
        audit=AuditLog(path=tmp_path / "audit2.jsonl"),
    )
    assert engine2.is_quarantined("persistent-task"), (
        "quarantine should be loaded from disk on restart"
    )


# ---------------------------------------------------------------------------
# Test 12: release_quarantine on non-quarantined id is a no-op
# ---------------------------------------------------------------------------

def test_release_quarantine_noop_on_unknown(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    # Should not raise
    engine.release_quarantine("never-healed-task")
    assert not engine.is_quarantined("never-healed-task")


# ---------------------------------------------------------------------------
# Test 13: quarantine.json is valid JSON after heal
# ---------------------------------------------------------------------------

def test_quarantine_json_is_valid(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    engine.heal("task-json-check")

    raw = _quarantine_path(tmp_path).read_text(encoding="utf-8")
    data = json.loads(raw)   # must not raise
    assert isinstance(data, dict)
    assert "quarantine" in data
    assert isinstance(data["quarantine"], list)


# ---------------------------------------------------------------------------
# Test 14: rolled_back_to is "none" when snapshot store is empty
# ---------------------------------------------------------------------------

def test_rolled_back_to_is_none_when_no_snapshots(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    result = engine.heal("task-no-snap")
    assert result.rolled_back_to == "none"


# ---------------------------------------------------------------------------
# Test 15: rolled_back_to is snapshot ts when a snapshot exists
# ---------------------------------------------------------------------------

def test_rolled_back_to_snapshot_ts(tmp_path, monkeypatch):
    snap_path = tmp_path / "snapshots.jsonl"
    store = SnapshotStore(path=snap_path)
    snap = SystemSnapshot(ts=9_999_999.0, campaigns_active=1)
    store.record(snap)

    engine = _make_engine(tmp_path, monkeypatch, snapshot_store=store)
    result = engine.heal("task-with-snap")
    assert result.rolled_back_to == str(9_999_999.0)


# ---------------------------------------------------------------------------
# Test 16: heal() publishes correct payload fields
# ---------------------------------------------------------------------------

def test_heal_publishes_correct_payload_fields(tmp_path, monkeypatch, isolated_bus):
    engine = _make_engine(tmp_path, monkeypatch, bus=isolated_bus)

    received: list[dict] = []
    isolated_bus.subscribe("system.self_heal", lambda t, p: received.append(p))

    engine.heal("task-payload", reason="test_reason")

    assert len(received) == 1
    p = received[0]
    assert p["task_id"] == "task-payload"
    assert p["reason"] == "test_reason"
    assert "snapshot_id" in p
    assert "ts" in p
    assert isinstance(p["ts"], float)


# ---------------------------------------------------------------------------
# Test 17: multiple tasks can be quarantined independently
# ---------------------------------------------------------------------------

def test_multiple_tasks_quarantined_independently(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    engine.heal("task-m1")
    engine.heal("task-m2")

    assert engine.is_quarantined("task-m1")
    assert engine.is_quarantined("task-m2")
    assert not engine.is_quarantined("task-m3")


# ---------------------------------------------------------------------------
# Test 18: release_quarantine removes only the specified task
# ---------------------------------------------------------------------------

def test_release_quarantine_removes_only_specified(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    engine.heal("task-r1")
    engine.heal("task-r2")

    engine.release_quarantine("task-r1")

    assert not engine.is_quarantined("task-r1")
    assert engine.is_quarantined("task-r2")


# ---------------------------------------------------------------------------
# Test 19: quarantine_list() returns a copy (mutating doesn't affect engine)
# ---------------------------------------------------------------------------

def test_quarantine_list_returns_copy(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    engine.heal("task-copy")

    lst = engine.quarantine_list()
    lst.clear()  # mutate the returned list

    # Engine should still report the task as quarantined
    assert engine.is_quarantined("task-copy")
    assert len(engine.quarantine_list()) == 1


# ---------------------------------------------------------------------------
# Test 20: audit entry correlation_id matches task_id
# ---------------------------------------------------------------------------

def test_audit_correlation_id_matches_task_id(tmp_path, monkeypatch):
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    engine = _make_engine(tmp_path, monkeypatch, audit=audit)
    engine.heal("task-corr-99")

    tail = audit.tail(10)
    matches = [r for r in tail if r.correlation_id == "task-corr-99"]
    assert matches, "expected audit record with correlation_id == 'task-corr-99'"


# ---------------------------------------------------------------------------
# Test 21: kernel integration — quarantine.json contains dead-lettered task_id
# ---------------------------------------------------------------------------

def test_kernel_integration_quarantine_json_contains_dead_lettered(tmp_path, monkeypatch):
    monkeypatch.setenv("PRADYOS_STATE_PATH", str(tmp_path))
    from pradyos.imperium.checkpoint import CheckpointStore

    kern = Imperium(
        audit=AuditLog(path=tmp_path / "audit.jsonl"),
        checkpoint=CheckpointStore(state_dir=tmp_path),
    )
    engine = SelfHealEngine(
        kernel=kern,
        bus=EventBus(),
        snapshot_store=SnapshotStore(path=tmp_path / "snapshots.jsonl"),
        audit=AuditLog(path=tmp_path / "audit2.jsonl"),
    )
    kern._self_heal_engine = engine

    task_id = _submit_failing_task(kern, max_retries=0)
    kern.run_one()

    path = _quarantine_path(tmp_path)
    assert path.exists(), "quarantine.json should be written"
    data = json.loads(path.read_text())
    assert task_id in data["quarantine"]


# ---------------------------------------------------------------------------
# Test 22: kernel integration — system.self_heal bus event fired
# ---------------------------------------------------------------------------

def test_kernel_integration_self_heal_bus_event_fired(tmp_path, monkeypatch):
    monkeypatch.setenv("PRADYOS_STATE_PATH", str(tmp_path))
    from pradyos.imperium.checkpoint import CheckpointStore

    bus = EventBus()
    fired: list[dict] = []
    bus.subscribe("system.self_heal", lambda t, p: fired.append(p))

    kern = Imperium(
        audit=AuditLog(path=tmp_path / "audit.jsonl"),
        bus=bus,
        checkpoint=CheckpointStore(state_dir=tmp_path),
    )
    engine = SelfHealEngine(
        kernel=kern,
        bus=bus,
        snapshot_store=SnapshotStore(path=tmp_path / "snapshots.jsonl"),
        audit=AuditLog(path=tmp_path / "audit2.jsonl"),
    )
    kern._self_heal_engine = engine

    task_id = _submit_failing_task(kern, max_retries=0)
    kern.run_one()

    assert fired, "system.self_heal bus event should have been published"
    assert fired[0]["task_id"] == task_id
    assert fired[0]["reason"] == "retry_budget_exhausted"
