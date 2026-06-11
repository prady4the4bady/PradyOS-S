"""Phase 67C — 20 tests for pradyos.core.process_manager.ProcessManager."""
from __future__ import annotations

import time

import pytest

from pradyos.core.process_manager import (
    HistoryEntry,
    ProcessInstance,
    ProcessManager,
)


# ── init / create ────────────────────────────────────────────────────────────

def test_init_has_zero_count():
    pm = ProcessManager()
    assert pm.count() == 0


def test_create_returns_process_instance():
    pm = ProcessManager()
    inst = pm.create("order", "pending")
    assert isinstance(inst, ProcessInstance)
    assert inst.process_name == "order"
    assert inst.state == "pending"


def test_create_stores_in_index():
    pm = ProcessManager()
    inst = pm.create("order", "pending")
    assert pm.get(inst.process_id) is inst


def test_create_default_context_is_empty_dict():
    pm = ProcessManager()
    inst = pm.create("order", "pending")
    assert inst.context == {}


def test_create_custom_context_stored():
    pm = ProcessManager()
    inst = pm.create("order", "pending", context={"customer": "alice", "total": 99})
    assert inst.context == {"customer": "alice", "total": 99}


# ── transition ──────────────────────────────────────────────────────────────

def test_transition_returns_updated_instance():
    pm = ProcessManager()
    inst = pm.create("order", "pending")
    result = pm.transition(inst.process_id, "approve", "approved")
    assert result is inst


def test_transition_unknown_id_returns_none():
    pm = ProcessManager()
    assert pm.transition("phantom", "x", "y") is None


def test_transition_updates_state():
    pm = ProcessManager()
    inst = pm.create("order", "pending")
    pm.transition(inst.process_id, "approve", "approved")
    assert inst.state == "approved"


def test_transition_shallow_merges_context_patch():
    pm = ProcessManager()
    inst = pm.create("order", "pending", context={"x": 1, "y": 2})
    pm.transition(inst.process_id, "set_y", "updated", context_patch={"y": 99, "z": 3})
    assert inst.context == {"x": 1, "y": 99, "z": 3}


def test_transition_appends_history_entry():
    pm = ProcessManager()
    inst = pm.create("order", "pending")
    pm.transition(inst.process_id, "approve", "approved")
    assert len(inst.history) == 1
    assert isinstance(inst.history[0], HistoryEntry)


def test_history_entry_has_correct_from_to_trigger():
    pm = ProcessManager()
    inst = pm.create("order", "pending")
    pm.transition(inst.process_id, "approve", "approved")
    h = inst.history[0]
    assert h.from_state == "pending"
    assert h.to_state == "approved"
    assert h.trigger == "approve"


def test_context_snapshot_is_state_after_patch():
    pm = ProcessManager()
    inst = pm.create("order", "pending", context={"x": 1})
    pm.transition(inst.process_id, "patch", "updated", context_patch={"x": 99, "y": 2})
    snap = inst.history[0].context_snapshot
    assert snap == {"x": 99, "y": 2}


def test_transition_without_patch_does_not_clear_context():
    pm = ProcessManager()
    inst = pm.create("order", "pending", context={"x": 1, "y": 2})
    pm.transition(inst.process_id, "noop", "approved")  # no patch
    assert inst.context == {"x": 1, "y": 2}


def test_two_transitions_produce_two_history_entries():
    pm = ProcessManager()
    inst = pm.create("order", "pending")
    pm.transition(inst.process_id, "approve", "approved")
    pm.transition(inst.process_id, "ship", "shipped")
    assert len(inst.history) == 2
    assert inst.history[0].to_state == "approved"
    assert inst.history[1].to_state == "shipped"


# ── list_processes ──────────────────────────────────────────────────────────

def test_list_processes_most_recently_updated_first():
    pm = ProcessManager()
    a = pm.create("a", "pending")
    time.sleep(0.001)
    b = pm.create("b", "pending")
    time.sleep(0.001)
    pm.transition(a.process_id, "approve", "approved")  # a is now newer
    listed = pm.list_processes()
    assert listed[0].process_id == a.process_id
    assert listed[1].process_id == b.process_id


def test_list_processes_filter_by_state():
    pm = ProcessManager()
    a = pm.create("a", "pending")
    b = pm.create("b", "pending")
    pm.transition(a.process_id, "approve", "approved")
    pending_only = pm.list_processes(state="pending")
    assert len(pending_only) == 1
    assert pending_only[0].process_id == b.process_id


def test_list_processes_limit_respected():
    pm = ProcessManager()
    for i in range(5):
        pm.create(f"p{i}", "pending")
    assert len(pm.list_processes(limit=3)) == 3


# ── delete / count ──────────────────────────────────────────────────────────

def test_delete_returns_true_and_removes():
    pm = ProcessManager()
    inst = pm.create("p", "pending")
    assert pm.delete(inst.process_id) is True
    assert pm.get(inst.process_id) is None


def test_delete_unknown_returns_false():
    pm = ProcessManager()
    assert pm.delete("phantom") is False


def test_count_by_state_correct():
    pm = ProcessManager()
    a = pm.create("a", "pending")
    pm.create("b", "pending")
    pm.create("c", "pending")
    pm.transition(a.process_id, "approve", "approved")
    assert pm.count() == 3
    assert pm.count(state="pending") == 2
    assert pm.count(state="approved") == 1
