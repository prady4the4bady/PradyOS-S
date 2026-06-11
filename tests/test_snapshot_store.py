"""Phase 32C — 20 tests for pradyos.core.snapshot_store.SnapshotStore."""
from __future__ import annotations

import json
import threading
import time

import pytest

from pradyos.core.snapshot_store import Snapshot, SnapshotStore


# ── helpers ───────────────────────────────────────────────────────────────────

def _store() -> SnapshotStore:
    return SnapshotStore()  # memory mode


# ── initialisation ────────────────────────────────────────────────────────────

def test_init_empty_memory_mode():
    ss = _store()
    assert ss._store == {}
    assert ss.count() == 0


# ── save ──────────────────────────────────────────────────────────────────────

def test_save_returns_snapshot():
    ss = _store()
    snap = ss.save("ns", "k", {"x": 1})
    assert isinstance(snap, Snapshot)
    assert snap.namespace == "ns"
    assert snap.key == "k"
    assert snap.data == {"x": 1}


def test_first_save_version_is_1():
    ss = _store()
    snap = ss.save("ns", "k", {})
    assert snap.version == 1


def test_second_save_same_key_version_is_2():
    ss = _store()
    ss.save("ns", "k", {"v": 1})
    snap2 = ss.save("ns", "k", {"v": 2})
    assert snap2.version == 2


# ── get ───────────────────────────────────────────────────────────────────────

def test_get_returns_latest_when_no_version():
    ss = _store()
    ss.save("ns", "k", {"v": 1})
    ss.save("ns", "k", {"v": 2})
    snap = ss.get("ns", "k")
    assert snap is not None
    assert snap.version == 2
    assert snap.data == {"v": 2}


def test_get_returns_specific_version():
    ss = _store()
    ss.save("ns", "k", {"v": 1})
    ss.save("ns", "k", {"v": 2})
    snap = ss.get("ns", "k", version=1)
    assert snap is not None
    assert snap.version == 1
    assert snap.data == {"v": 1}


def test_get_returns_none_for_unknown_key():
    ss = _store()
    assert ss.get("ns", "missing") is None


def test_get_returns_none_for_unknown_version():
    ss = _store()
    ss.save("ns", "k", {})
    assert ss.get("ns", "k", version=99) is None


# ── list_keys ─────────────────────────────────────────────────────────────────

def test_list_keys_sorted():
    ss = _store()
    ss.save("ns", "zzz", {})
    ss.save("ns", "aaa", {})
    ss.save("ns", "mmm", {})
    keys = [e["key"] for e in ss.list_keys("ns")]
    assert keys == ["aaa", "mmm", "zzz"]


def test_list_keys_entry_has_required_keys():
    ss = _store()
    ss.save("ns", "k", {})
    entry = ss.list_keys("ns")[0]
    for field in ("key", "versions", "latest_version", "latest_saved_at"):
        assert field in entry, f"Missing field: {field}"


def test_list_keys_versions_count_correct():
    ss = _store()
    ss.save("ns", "k", {})
    ss.save("ns", "k", {})
    ss.save("ns", "k", {})
    entry = ss.list_keys("ns")[0]
    assert entry["versions"] == 3
    assert entry["latest_version"] == 3


def test_list_keys_empty_for_unknown_namespace():
    ss = _store()
    assert ss.list_keys("no-such-ns") == []


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_returns_true_and_removes():
    ss = _store()
    ss.save("ns", "k", {})
    assert ss.delete("ns", "k") is True
    assert ss.get("ns", "k") is None


def test_delete_returns_false_for_unknown():
    ss = _store()
    assert ss.delete("ns", "phantom") is False


# ── count ─────────────────────────────────────────────────────────────────────

def test_count_total_across_all_namespaces():
    ss = _store()
    ss.save("a", "k1", {})
    ss.save("a", "k1", {})
    ss.save("b", "k2", {})
    assert ss.count() == 3


def test_count_scoped_to_namespace():
    ss = _store()
    ss.save("a", "k1", {})
    ss.save("a", "k1", {})
    ss.save("b", "k2", {})
    assert ss.count("a") == 2
    assert ss.count("b") == 1


# ── file mode ─────────────────────────────────────────────────────────────────

def test_file_mode_persists_to_jsonl(tmp_path):
    ss = SnapshotStore(base_dir=tmp_path)
    ss.save("ns", "k", {"hello": "world"})
    jsonl = tmp_path / "ns.jsonl"
    assert jsonl.exists()
    records = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    assert len(records) == 1
    assert records[0]["data"] == {"hello": "world"}


def test_file_mode_reloads_on_reinit(tmp_path):
    ss1 = SnapshotStore(base_dir=tmp_path)
    ss1.save("ns", "k", {"hello": "world"})
    ss2 = SnapshotStore(base_dir=tmp_path)
    assert ss2.count("ns") == 1


def test_file_mode_reloaded_get_correct_snapshot(tmp_path):
    ss1 = SnapshotStore(base_dir=tmp_path)
    ss1.save("ns", "k", {"value": 42})
    ss2 = SnapshotStore(base_dir=tmp_path)
    snap = ss2.get("ns", "k")
    assert snap is not None
    assert snap.data == {"value": 42}
    assert snap.version == 1


# ── thread safety ─────────────────────────────────────────────────────────────

def test_thread_safety_concurrent_saves():
    ss = _store()
    errors: list[Exception] = []

    def worker():
        try:
            ss.save("ns", "k", {"t": time.time()})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert ss.count("ns") == 50
    # versions must be 1..50 with no gaps
    versions = {v for v in ss._store["ns"]["k"]}
    assert versions == set(range(1, 51))
