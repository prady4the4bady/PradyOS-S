"""Phase 36C — 20 tests for pradyos.core.state_manager.StateManager."""
from __future__ import annotations

import pytest

from pradyos.core.state_manager import StateManager
from pradyos.core.snapshot_store import SnapshotStore


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_no_store_status():
    sm = StateManager()
    assert sm.status()["store_connected"] is False


# ── register_module ───────────────────────────────────────────────────────────

def test_register_module_adds_to_list():
    sm = StateManager()
    sm.register_module("intent")
    assert "intent" in sm.status()["registered_modules"]


def test_register_module_no_duplicates():
    sm = StateManager()
    sm.register_module("intent")
    sm.register_module("intent")
    sm.register_module("intent")
    mods = sm.status()["registered_modules"]
    assert mods.count("intent") == 1


# ── save_state ────────────────────────────────────────────────────────────────

def test_save_state_returns_none_when_no_store():
    sm = StateManager()
    assert sm.save_state("ns", "k", {"x": 1}) is None


def test_save_state_returns_dict_when_store_present():
    sm = StateManager(snapshot_store=SnapshotStore())
    result = sm.save_state("ns", "k", {"x": 1})
    assert isinstance(result, dict)


def test_save_state_returned_dict_has_version():
    sm = StateManager(snapshot_store=SnapshotStore())
    result = sm.save_state("ns", "k", {"x": 1})
    assert "version" in result
    assert result["version"] == 1


# ── load_state ────────────────────────────────────────────────────────────────

def test_load_state_returns_none_when_no_store():
    sm = StateManager()
    assert sm.load_state("ns", "k") is None


def test_load_state_returns_dict_after_save():
    sm = StateManager(snapshot_store=SnapshotStore())
    sm.save_state("ns", "k", {"hello": "world"})
    result = sm.load_state("ns", "k")
    assert result is not None
    assert result["data"] == {"hello": "world"}


def test_load_state_returns_none_for_unknown_key():
    sm = StateManager(snapshot_store=SnapshotStore())
    assert sm.load_state("ns", "phantom") is None


def test_load_state_version_param_returns_specific():
    sm = StateManager(snapshot_store=SnapshotStore())
    sm.save_state("ns", "k", {"v": 1})
    sm.save_state("ns", "k", {"v": 2})
    result = sm.load_state("ns", "k", version=1)
    assert result is not None
    assert result["data"] == {"v": 1}


# ── register_hook ─────────────────────────────────────────────────────────────

def test_register_hook_appends():
    sm = StateManager()
    sm.register_hook("h1", lambda: None)
    assert sm.status()["hook_count"] == 1


# ── shutdown ──────────────────────────────────────────────────────────────────

def test_shutdown_returns_list():
    sm = StateManager()
    sm.register_hook("h1", lambda: None)
    results = sm.shutdown()
    assert isinstance(results, list)


def test_shutdown_result_contains_name_ok():
    sm = StateManager()
    sm.register_hook("h1", lambda: None)
    results = sm.shutdown()
    assert "h1:ok" in results


def test_shutdown_continues_after_error_records_error():
    sm = StateManager()

    def bad_hook():
        raise RuntimeError("boom")

    sm.register_hook("bad", bad_hook)
    sm.register_hook("good", lambda: None)
    results = sm.shutdown()
    assert any(r.startswith("bad:error:") for r in results)
    assert "good:ok" in results


def test_shutdown_fires_hooks_in_order():
    sm = StateManager()
    order: list[str] = []
    sm.register_hook("first", lambda: order.append("first"))
    sm.register_hook("second", lambda: order.append("second"))
    sm.register_hook("third", lambda: order.append("third"))
    sm.shutdown()
    assert order == ["first", "second", "third"]


def test_shutdown_empty_returns_empty_list():
    sm = StateManager()
    assert sm.shutdown() == []


# ── status ────────────────────────────────────────────────────────────────────

def test_status_has_required_keys():
    sm = StateManager()
    s = sm.status()
    for key in ("store_connected", "registered_modules", "hook_count"):
        assert key in s, f"Missing key: {key}"


def test_status_store_connected_true_when_set():
    sm = StateManager(snapshot_store=SnapshotStore())
    assert sm.status()["store_connected"] is True


def test_status_registered_modules_reflects_calls():
    sm = StateManager()
    sm.register_module("a")
    sm.register_module("b")
    mods = sm.status()["registered_modules"]
    assert "a" in mods
    assert "b" in mods


def test_status_hook_count_reflects_calls():
    sm = StateManager()
    sm.register_hook("h1", lambda: None)
    sm.register_hook("h2", lambda: None)
    sm.register_hook("h3", lambda: None)
    assert sm.status()["hook_count"] == 3
