"""Tests for pradyos.core.snapshot — SystemSnapshot + SnapshotStore.

All tests are fully self-contained: use tmp_path, no real disk state.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from pradyos.core.snapshot import SnapshotStore, SystemSnapshot


# ---------------------------------------------------------------------------
# SystemSnapshot
# ---------------------------------------------------------------------------


def test_snapshot_defaults():
    s = SystemSnapshot()
    assert s.campaigns_active == 0
    assert s.tasks_pending == 0
    assert isinstance(s.ts, float)
    assert isinstance(s.metadata, dict)


def test_snapshot_to_dict_roundtrip():
    s = SystemSnapshot(
        ts=1_000_000.0,
        campaigns_active=3,
        campaigns_total=10,
        tasks_pending=2,
        tasks_running=1,
        tasks_completed=7,
        incidents_open=0,
        memory_records=42,
        metadata={"node": "alpha"},
    )
    d = s.to_dict()
    assert d["campaigns_active"] == 3
    assert d["metadata"]["node"] == "alpha"

    s2 = SystemSnapshot.from_dict(d)
    assert s2.ts == 1_000_000.0
    assert s2.campaigns_total == 10
    assert s2.memory_records == 42
    assert s2.metadata["node"] == "alpha"


def test_snapshot_from_dict_missing_keys():
    # from_dict should tolerate missing fields with sensible defaults
    s = SystemSnapshot.from_dict({})
    assert s.campaigns_active == 0
    assert s.incidents_open == 0


# ---------------------------------------------------------------------------
# SnapshotStore — record + read roundtrip
# ---------------------------------------------------------------------------


def test_record_and_latest(tmp_path):
    store = SnapshotStore(path=tmp_path / "snaps.jsonl")

    s1 = SystemSnapshot(ts=1.0, campaigns_active=1)
    s2 = SystemSnapshot(ts=2.0, campaigns_active=2)
    s3 = SystemSnapshot(ts=3.0, campaigns_active=3)

    store.record(s1)
    store.record(s2)
    store.record(s3)

    results = store.latest(10)
    assert len(results) == 3
    # newest first
    assert results[0].ts == 3.0
    assert results[1].ts == 2.0
    assert results[2].ts == 1.0


def test_latest_ordering_newest_first(tmp_path):
    store = SnapshotStore(path=tmp_path / "snaps.jsonl")
    for i in range(10):
        store.record(SystemSnapshot(ts=float(i)))

    results = store.latest(5)
    assert len(results) == 5
    # should be 9, 8, 7, 6, 5
    assert results[0].ts == 9.0
    assert results[-1].ts == 5.0


def test_latest_returns_empty_when_no_file(tmp_path):
    store = SnapshotStore(path=tmp_path / "nonexistent.jsonl")
    assert store.latest() == []


def test_latest_n_limits_results(tmp_path):
    store = SnapshotStore(path=tmp_path / "snaps.jsonl")
    for i in range(20):
        store.record(SystemSnapshot(ts=float(i)))

    results = store.latest(3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# SnapshotStore — prune
# ---------------------------------------------------------------------------


def test_prune_removes_old_entries(tmp_path):
    store = SnapshotStore(path=tmp_path / "snaps.jsonl")
    for i in range(10):
        store.record(SystemSnapshot(ts=float(i)))

    removed = store.prune(keep=5)
    assert removed == 5

    remaining = store.latest(100)
    assert len(remaining) == 5
    # newest first: 9, 8, 7, 6, 5
    assert remaining[0].ts == 9.0
    assert remaining[-1].ts == 5.0


def test_prune_noop_when_under_limit(tmp_path):
    store = SnapshotStore(path=tmp_path / "snaps.jsonl")
    for i in range(3):
        store.record(SystemSnapshot(ts=float(i)))

    removed = store.prune(keep=10)
    assert removed == 0
    assert len(store.latest(100)) == 3


def test_prune_noop_when_no_file(tmp_path):
    store = SnapshotStore(path=tmp_path / "nonexistent.jsonl")
    assert store.prune(keep=100) == 0


# ---------------------------------------------------------------------------
# SnapshotStore — concurrent writes don't corrupt
# ---------------------------------------------------------------------------


def test_concurrent_writes_no_corruption(tmp_path):
    path = tmp_path / "concurrent.jsonl"
    store = SnapshotStore(path=path)

    errors: list[Exception] = []
    n_threads = 8
    writes_per_thread = 25

    def writer(thread_id: int) -> None:
        try:
            for i in range(writes_per_thread):
                store.record(SystemSnapshot(ts=float(thread_id * 1000 + i),
                                            metadata={"thread": thread_id, "i": i}))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == [], f"Concurrent write errors: {errors}"

    # Every line in the file must be valid JSON with required fields
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == n_threads * writes_per_thread

    for line in lines:
        d = json.loads(line)  # must not raise
        assert "ts" in d


# ---------------------------------------------------------------------------
# SnapshotStore — parent dir creation
# ---------------------------------------------------------------------------


def test_record_creates_parent_dirs(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "snaps.jsonl"
    store = SnapshotStore(path=deep)
    store.record(SystemSnapshot(ts=99.0))
    assert deep.exists()
    lines = [l for l in deep.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["ts"] == 99.0
