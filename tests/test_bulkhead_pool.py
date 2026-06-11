"""Phase 55C — 20 tests for pradyos.core.bulkhead_pool.{BulkheadPool, BulkheadManager}."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.bulkhead_pool import (
    BulkheadManager,
    BulkheadPool,
    BulkheadRejectedError,
    PoolStats,
)


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.005) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ── BulkheadPool basics ───────────────────────────────────────────────────────

def test_init_correct_max_workers_and_queue_depth():
    pool = BulkheadPool(max_workers=3, queue_depth=5, name="svc")
    try:
        s = pool.get_stats()
        assert s.max_workers == 3
        assert s.queue_depth == 5
    finally:
        pool.shutdown()


def test_submit_returns_future():
    pool = BulkheadPool(max_workers=2, queue_depth=4)
    try:
        f = pool.submit(lambda: "ok")
        assert f.result(timeout=2.0) == "ok"
    finally:
        pool.shutdown()


def test_submitted_counter_increments():
    pool = BulkheadPool(max_workers=2, queue_depth=4)
    try:
        pool.submit(lambda: "ok").result(timeout=2.0)
        pool.submit(lambda: "ok").result(timeout=2.0)
        assert pool.get_stats().submitted == 2
    finally:
        pool.shutdown()


def test_completed_counter_increments_after_future_done():
    pool = BulkheadPool(max_workers=2, queue_depth=4)
    try:
        f = pool.submit(lambda: "ok")
        f.result(timeout=2.0)
        # done_callback may fire slightly after .result() returns
        assert _wait_until(lambda: pool.get_stats().completed == 1)
    finally:
        pool.shutdown()


# ── rejection ─────────────────────────────────────────────────────────────────

def test_rejected_counter_increments_when_at_capacity():
    pool = BulkheadPool(max_workers=1, queue_depth=0)
    gate = threading.Event()

    def slow():
        gate.wait(timeout=2.0)

    try:
        pool.submit(slow)  # in-flight = 1, capacity = 1
        with pytest.raises(BulkheadRejectedError):
            pool.submit(lambda: "x")
        assert pool.get_stats().rejected == 1
    finally:
        gate.set()
        pool.shutdown()


def test_bulkhead_rejected_error_raised_when_at_capacity():
    pool = BulkheadPool(max_workers=1, queue_depth=0)
    gate = threading.Event()
    try:
        pool.submit(lambda: gate.wait(timeout=2.0))
        with pytest.raises(BulkheadRejectedError):
            pool.submit(lambda: "x")
    finally:
        gate.set()
        pool.shutdown()


# ── reset_stats / get_stats ───────────────────────────────────────────────────

def test_reset_stats_zeroes_counters():
    pool = BulkheadPool(max_workers=2, queue_depth=4)
    try:
        pool.submit(lambda: "ok").result(timeout=2.0)
        assert _wait_until(lambda: pool.get_stats().completed == 1)
        pool.reset_stats()
        s = pool.get_stats()
        assert s.submitted == 0
        assert s.completed == 0
        assert s.rejected == 0
    finally:
        pool.shutdown()


def test_get_stats_returns_poolstats():
    pool = BulkheadPool(max_workers=2, queue_depth=4)
    try:
        assert isinstance(pool.get_stats(), PoolStats)
    finally:
        pool.shutdown()


def test_poolstats_to_dict_has_required_keys():
    pool = BulkheadPool(max_workers=2, queue_depth=4)
    try:
        d = pool.get_stats().to_dict()
        for k in ("name", "max_workers", "queue_depth", "submitted",
                  "completed", "rejected", "active"):
            assert k in d
    finally:
        pool.shutdown()


def test_shutdown_does_not_raise():
    pool = BulkheadPool(max_workers=2, queue_depth=4)
    pool.shutdown()  # should not raise


# ── BulkheadManager ──────────────────────────────────────────────────────────

def test_manager_creates_pool():
    mgr = BulkheadManager()
    try:
        pool = mgr.create("svc")
        assert isinstance(pool, BulkheadPool)
        assert mgr.count() == 1
    finally:
        mgr.delete("svc")


def test_manager_get_returns_pool():
    mgr = BulkheadManager()
    try:
        created = mgr.create("svc")
        assert mgr.get("svc") is created
    finally:
        mgr.delete("svc")


def test_manager_get_unknown_returns_none():
    mgr = BulkheadManager()
    assert mgr.get("phantom") is None


def test_manager_create_duplicate_raises_valueerror():
    mgr = BulkheadManager()
    try:
        mgr.create("svc")
        with pytest.raises(ValueError):
            mgr.create("svc")
    finally:
        mgr.delete("svc")


def test_manager_delete_returns_true_removes_pool():
    mgr = BulkheadManager()
    mgr.create("svc")
    assert mgr.delete("svc") is True
    assert mgr.get("svc") is None


def test_manager_delete_unknown_returns_false():
    mgr = BulkheadManager()
    assert mgr.delete("phantom") is False


def test_manager_list_pools_sorted_by_name():
    mgr = BulkheadManager()
    try:
        mgr.create("zzz")
        mgr.create("aaa")
        mgr.create("mmm")
        names = [p["name"] for p in mgr.list_pools()]
        assert names == ["aaa", "mmm", "zzz"]
    finally:
        for n in ("aaa", "mmm", "zzz"):
            mgr.delete(n)


def test_manager_count_correct():
    mgr = BulkheadManager()
    try:
        mgr.create("a")
        mgr.create("b")
        assert mgr.count() == 2
    finally:
        mgr.delete("a")
        mgr.delete("b")


# ── concurrency ───────────────────────────────────────────────────────────────

def test_thread_safety_30_concurrent_submits_all_succeed():
    pool = BulkheadPool(max_workers=4, queue_depth=100)  # plenty of capacity
    errors: list[Exception] = []
    futures: list = []

    def worker():
        try:
            f = pool.submit(lambda: "ok")
            futures.append(f)
        except Exception as exc:
            errors.append(exc)

    try:
        threads = [threading.Thread(target=worker) for _ in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for f in futures:
            f.result(timeout=2.0)
        assert errors == []
        assert pool.get_stats().submitted == 30
    finally:
        pool.shutdown()


def test_5_concurrent_submits_capacity_1_at_least_1_rejected():
    pool = BulkheadPool(max_workers=1, queue_depth=0)
    gate = threading.Event()

    def slow():
        gate.wait(timeout=2.0)

    rejected = [0]
    accepted = [0]

    def submit_one():
        try:
            pool.submit(slow)
            accepted[0] += 1
        except BulkheadRejectedError:
            rejected[0] += 1

    try:
        threads = [threading.Thread(target=submit_one) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert rejected[0] >= 1
        assert accepted[0] + rejected[0] == 5
    finally:
        gate.set()
        pool.shutdown()
