"""Phase 66C — 20 tests for pradyos.core.saga_orchestrator.SagaOrchestrator."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.saga_orchestrator import SagaOrchestrator, SagaRun


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty_handlers_empty_runs():
    so = SagaOrchestrator()
    assert so.list_handlers() == []
    assert so.list_runs() == []


# ── register / unregister ────────────────────────────────────────────────────

def test_register_stores_handler():
    so = SagaOrchestrator()
    so.register("double", lambda p: {"n": p.get("n", 0) * 2})
    assert "double" in so.list_handlers()


def test_register_overwrites_no_error():
    so = SagaOrchestrator()
    so.register("h", lambda p: {"v": 1})
    so.register("h", lambda p: {"v": 2})
    run = so.run("s", ["h"], {})
    assert run.status == "completed"
    assert run.payload_trace[0]["output"] == {"v": 2}


def test_unregister_returns_true_removes():
    so = SagaOrchestrator()
    so.register("h", lambda p: {})
    assert so.unregister("h") is True
    assert "h" not in so.list_handlers()


def test_unregister_unknown_returns_false():
    so = SagaOrchestrator()
    assert so.unregister("phantom") is False


def test_list_handlers_sorted():
    so = SagaOrchestrator()
    so.register("zzz", lambda p: {})
    so.register("aaa", lambda p: {})
    so.register("mmm", lambda p: {})
    assert so.list_handlers() == ["aaa", "mmm", "zzz"]


# ── run ──────────────────────────────────────────────────────────────────────

def test_run_no_steps_completes_immediately():
    so = SagaOrchestrator()
    run = so.run("empty", [], {})
    assert run.status == "completed"
    assert run.payload_trace == []
    assert run.finished_at is not None


def test_run_single_step_completed():
    so = SagaOrchestrator()
    so.register("ping", lambda p: {"pong": True})
    run = so.run("s", ["ping"], {})
    assert run.status == "completed"


def test_run_single_step_payload_trace_has_input_output():
    so = SagaOrchestrator()
    so.register("double", lambda p: {"n": p.get("n", 0) * 2})
    run = so.run("s", ["double"], {"n": 5})
    assert len(run.payload_trace) == 1
    entry = run.payload_trace[0]
    assert entry["step"] == "double"
    assert entry["input"] == {"n": 5}
    assert entry["output"] == {"n": 10}


def test_run_multi_step_chains_output_to_input():
    so = SagaOrchestrator()
    so.register("double", lambda p: {"n": p.get("n", 0) * 2})
    so.register("add_one", lambda p: {"n": p.get("n", 0) + 1})
    # n=5 → double → 10 → add_one → 11
    run = so.run("chain", ["double", "add_one"], {"n": 5})
    assert run.status == "completed"
    assert run.payload_trace[1]["input"] == {"n": 10}
    assert run.payload_trace[1]["output"] == {"n": 11}


def test_run_multi_step_all_succeed_finished_at_set():
    so = SagaOrchestrator()
    so.register("a", lambda p: {"a": 1})
    so.register("b", lambda p: {"b": 2})
    run = so.run("s", ["a", "b"], {})
    assert run.status == "completed"
    assert run.finished_at is not None
    assert run.finished_at >= run.started_at


def test_run_unknown_step_name_fails_with_step_in_error():
    so = SagaOrchestrator()
    so.register("known", lambda p: {})
    run = so.run("s", ["known", "phantom"], {})
    assert run.status == "failed"
    assert "phantom" in run.error


def test_run_handler_exception_fails_with_exc_message():
    so = SagaOrchestrator()
    so.register("bad", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    run = so.run("s", ["bad"], {})
    assert run.status == "failed"
    assert "boom" in run.error


def test_failed_run_stops_at_failing_step():
    so = SagaOrchestrator()
    so.register("ok1", lambda p: {"ok": 1})
    so.register("bad", lambda p: (_ for _ in ()).throw(RuntimeError("nope")))
    so.register("ok2", lambda p: {"ok": 2})
    run = so.run("s", ["ok1", "bad", "ok2"], {})
    assert run.status == "failed"
    # payload_trace has ok1 (output) and bad (error) — NO ok2 entry
    steps_in_trace = [e["step"] for e in run.payload_trace]
    assert "ok2" not in steps_in_trace
    assert len(run.payload_trace) == 2


# ── introspection ────────────────────────────────────────────────────────────

def test_get_returns_saga_run_by_id():
    so = SagaOrchestrator()
    so.register("h", lambda p: {})
    run = so.run("s", ["h"], {})
    assert so.get(run.saga_id) is run


def test_get_returns_none_for_unknown_id():
    so = SagaOrchestrator()
    assert so.get("phantom") is None


def test_list_runs_most_recent_first():
    so = SagaOrchestrator()
    so.register("h", lambda p: {})
    r1 = so.run("s", ["h"], {})
    r2 = so.run("s", ["h"], {})
    r3 = so.run("s", ["h"], {})
    ids = [r.saga_id for r in so.list_runs()]
    assert ids == [r3.saga_id, r2.saga_id, r1.saga_id]


def test_list_runs_limit_respected():
    so = SagaOrchestrator()
    so.register("h", lambda p: {})
    for _ in range(10):
        so.run("s", ["h"], {})
    assert len(so.list_runs(limit=3)) == 3


def test_clear_returns_count_empties():
    so = SagaOrchestrator()
    so.register("h", lambda p: {})
    so.run("s", ["h"], {})
    so.run("s", ["h"], {})
    so.run("s", ["h"], {})
    n = so.clear()
    assert n == 3
    assert so.list_runs() == []


# ── concurrency ──────────────────────────────────────────────────────────────

def test_thread_safety_20_concurrent_runs():
    so = SagaOrchestrator()
    so.register("h", lambda p: {"ok": True})
    errors: list[Exception] = []
    run_ids: list[str] = []
    lock = threading.Lock()

    def worker():
        try:
            r = so.run("s", ["h"], {})
            with lock:
                run_ids.append(r.saga_id)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(run_ids) == 20
    # All run_ids must be findable via .get()
    for rid in run_ids:
        assert so.get(rid) is not None
