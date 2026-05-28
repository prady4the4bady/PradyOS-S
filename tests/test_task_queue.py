"""Phase 49C — 20 tests for pradyos.core.task_queue.TaskQueue + WorkerPool."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.task_queue import Task, TaskQueue, WorkerPool


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.01) -> bool:
    """Poll until predicate() is truthy or timeout. Returns final value."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ── TaskQueue basics ──────────────────────────────────────────────────────────

def test_init_empty():
    tq = TaskQueue()
    assert tq._tasks == {}


def test_submit_returns_pending_task():
    tq = TaskQueue()
    t = tq.submit("noop", {"k": "v"})
    assert isinstance(t, Task)
    assert t.status == "pending"


def test_submit_assigns_uuid_hex_id():
    tq = TaskQueue()
    t = tq.submit("noop", {})
    assert isinstance(t.id, str)
    int(t.id, 16)  # uuid hex is parseable


def test_submit_stores_task_get_works():
    tq = TaskQueue()
    t = tq.submit("noop", {})
    assert tq.get(t.id) is t


def test_get_unknown_returns_none():
    tq = TaskQueue()
    assert tq.get("phantom") is None


# ── list_tasks ────────────────────────────────────────────────────────────────

def test_list_tasks_sorted_by_created_at():
    tq = TaskQueue()
    t1 = tq.submit("a", {})
    time.sleep(0.001)
    t2 = tq.submit("b", {})
    time.sleep(0.001)
    t3 = tq.submit("c", {})
    ids = [t.id for t in tq.list_tasks()]
    assert ids == [t1.id, t2.id, t3.id]


def test_list_tasks_filter_pending():
    tq = TaskQueue()
    t1 = tq.submit("a", {})
    t2 = tq.submit("b", {})
    tq._mark_done(t1.id, {})
    pending = tq.list_tasks(status="pending")
    assert [t.id for t in pending] == [t2.id]


def test_list_tasks_filter_done():
    tq = TaskQueue()
    t1 = tq.submit("a", {})
    tq.submit("b", {})  # still pending
    tq._mark_done(t1.id, {"ok": True})
    done = tq.list_tasks(status="done")
    assert len(done) == 1
    assert done[0].id == t1.id


# ── cancel ────────────────────────────────────────────────────────────────────

def test_cancel_pending_sets_failed_cancelled():
    tq = TaskQueue()
    t = tq.submit("a", {})
    assert tq.cancel(t.id) is True
    fetched = tq.get(t.id)
    assert fetched.status == "failed"
    assert fetched.error == "cancelled"


def test_cancel_non_pending_returns_false():
    tq = TaskQueue()
    t = tq.submit("a", {})
    tq._mark_running(t.id)
    assert tq.cancel(t.id) is False


def test_cancel_unknown_returns_false():
    tq = TaskQueue()
    assert tq.cancel("phantom") is False


# ── state transition helpers ─────────────────────────────────────────────────

def test_mark_running_sets_status_and_started_at():
    tq = TaskQueue()
    t = tq.submit("a", {})
    tq._mark_running(t.id)
    fetched = tq.get(t.id)
    assert fetched.status == "running"
    assert fetched.started_at is not None


def test_mark_done_sets_result_and_finished_at():
    tq = TaskQueue()
    t = tq.submit("a", {})
    tq._mark_done(t.id, {"value": 42})
    fetched = tq.get(t.id)
    assert fetched.status == "done"
    assert fetched.result == {"value": 42}
    assert fetched.finished_at is not None


def test_mark_failed_sets_error_and_finished_at():
    tq = TaskQueue()
    t = tq.submit("a", {})
    tq._mark_failed(t.id, "boom")
    fetched = tq.get(t.id)
    assert fetched.status == "failed"
    assert fetched.error == "boom"
    assert fetched.finished_at is not None


# ── Task.to_dict ──────────────────────────────────────────────────────────────

def test_task_to_dict_has_all_keys():
    tq = TaskQueue()
    t = tq.submit("a", {"x": 1})
    d = t.to_dict()
    for key in ("id", "name", "payload", "priority", "status", "created_at",
                "started_at", "finished_at", "result", "error"):
        assert key in d


# ── WorkerPool ────────────────────────────────────────────────────────────────

def test_worker_executes_and_marks_done():
    tq = TaskQueue()
    seen = []

    def handler(task):
        seen.append(task.payload)
        return {"ok": True}

    pool = WorkerPool(tq, num_workers=1, handler=handler)
    try:
        t = tq.submit("ping", {"v": 1})
        assert _wait_until(lambda: tq.get(t.id).status == "done", timeout=2.0)
        fetched = tq.get(t.id)
        assert fetched.result == {"ok": True}
        assert seen == [{"v": 1}]
    finally:
        pool.stop()


def test_worker_marks_failed_on_handler_exception():
    tq = TaskQueue()

    def handler(task):
        raise RuntimeError("boom")

    pool = WorkerPool(tq, num_workers=1, handler=handler)
    try:
        t = tq.submit("bad", {})
        assert _wait_until(lambda: tq.get(t.id).status == "failed", timeout=2.0)
        assert tq.get(t.id).error == "boom"
    finally:
        pool.stop()


def test_worker_pool_stop_allows_clean_shutdown():
    tq = TaskQueue()
    pool = WorkerPool(tq, num_workers=2, handler=lambda t: {})
    pool.stop()
    # After stop, threads should be dead within a brief window
    assert _wait_until(lambda: not pool.is_alive(), timeout=2.0)


# ── concurrency ───────────────────────────────────────────────────────────────

def test_thread_safety_50_concurrent_submits():
    tq = TaskQueue()
    errors: list[Exception] = []

    def worker(i: int):
        try:
            tq.submit(f"t{i}", {"i": i})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(tq.list_tasks()) == 50


def test_worker_pool_3_workers_processes_10_tasks():
    tq = TaskQueue()

    def handler(task):
        time.sleep(0.01)
        return {"v": task.payload.get("v")}

    pool = WorkerPool(tq, num_workers=3, handler=handler)
    try:
        tasks = [tq.submit("job", {"v": i}) for i in range(10)]

        def all_done():
            return all(tq.get(t.id).status == "done" for t in tasks)

        assert _wait_until(all_done, timeout=5.0)
    finally:
        pool.stop()
