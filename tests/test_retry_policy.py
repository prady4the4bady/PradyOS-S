"""Phase 54C — 20 tests for pradyos.core.retry_policy.RetryPolicy."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.retry_policy import AttemptRecord, RetryPolicy


def _make_failing_fn(fail_count: int, exc_type=RuntimeError):
    """Return a fn that raises exc_type the first `fail_count` calls, then returns 'ok'."""
    counter = {"n": 0}

    def fn():
        counter["n"] += 1
        if counter["n"] <= fail_count:
            raise exc_type(f"fail-{counter['n']}")
        return "ok"

    return fn


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty_history():
    p = RetryPolicy()
    assert p._history == {}


# ── execute success path ─────────────────────────────────────────────────────

def test_execute_success_first_attempt_returns_value():
    p = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0)
    assert p.execute("svc", lambda: "ok") == "ok"


def test_execute_records_success_outcome():
    p = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0)
    p.execute("svc", lambda: "ok")
    hist = p.get_history("svc")
    assert len(hist) == 1
    assert hist[0]["outcome"] == "success"


def test_execute_success_after_two_failures():
    p = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0)
    fn = _make_failing_fn(fail_count=2)
    assert p.execute("svc", fn) == "ok"
    hist = p.get_history("svc")
    assert len(hist) == 3
    assert [h["outcome"] for h in hist] == ["failure", "failure", "success"]


# ── exhausted path ───────────────────────────────────────────────────────────

def test_execute_exhausted_raises_original_exception():
    p = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0)
    fn = _make_failing_fn(fail_count=999)
    with pytest.raises(RuntimeError, match="fail-3"):
        p.execute("svc", fn)


def test_exhausted_last_record_has_exhausted_outcome():
    p = RetryPolicy(max_attempts=3, base_delay=0.0, jitter=0.0)
    fn = _make_failing_fn(fail_count=999)
    with pytest.raises(RuntimeError):
        p.execute("svc", fn)
    hist = p.get_history("svc")
    assert len(hist) == 3
    assert hist[-1]["outcome"] == "exhausted"


# ── non-retry_on exception path ──────────────────────────────────────────────

def test_non_retry_on_exception_reraises_immediately():
    p = RetryPolicy(max_attempts=5, base_delay=0.0, jitter=0.0,
                    retry_on=(ValueError,))
    fn = _make_failing_fn(fail_count=999, exc_type=RuntimeError)
    with pytest.raises(RuntimeError):
        p.execute("svc", fn)
    assert len(p.get_history("svc")) == 1  # only one attempt


def test_non_retry_on_records_failure_outcome():
    p = RetryPolicy(max_attempts=5, retry_on=(ValueError,))
    with pytest.raises(RuntimeError):
        p.execute("svc", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    hist = p.get_history("svc")
    assert hist[0]["outcome"] == "failure"


# ── sleep computation (non-negative under jitter) ────────────────────────────

def test_sleep_never_negative_under_jitter():
    p = RetryPolicy(base_delay=0.0, backoff_factor=2.0, jitter=10.0)
    for attempt in range(1, 10):
        assert p._compute_sleep(attempt) >= 0.0


# ── get_history / clear_history ──────────────────────────────────────────────

def test_get_history_returns_list_of_dicts():
    p = RetryPolicy(base_delay=0.0)
    p.execute("svc", lambda: "ok")
    hist = p.get_history("svc")
    assert isinstance(hist, list)
    assert isinstance(hist[0], dict)


def test_get_history_unknown_returns_empty():
    p = RetryPolicy()
    assert p.get_history("phantom") == []


def test_clear_history_returns_true_empties():
    p = RetryPolicy(base_delay=0.0)
    p.execute("svc", lambda: "ok")
    assert p.clear_history("svc") is True
    assert p.get_history("svc") == []


def test_clear_history_unknown_returns_false():
    p = RetryPolicy()
    assert p.clear_history("phantom") is False


# ── list_names ───────────────────────────────────────────────────────────────

def test_list_names_sorted():
    p = RetryPolicy(base_delay=0.0)
    p.execute("zzz", lambda: "ok")
    p.execute("aaa", lambda: "ok")
    p.execute("mmm", lambda: "ok")
    assert p.list_names() == ["aaa", "mmm", "zzz"]


def test_list_names_empty():
    assert RetryPolicy().list_names() == []


# ── count ─────────────────────────────────────────────────────────────────────

def test_count_total_across_names():
    p = RetryPolicy(base_delay=0.0)
    p.execute("a", lambda: "ok")
    p.execute("a", lambda: "ok")
    p.execute("b", lambda: "ok")
    assert p.count() == 3


def test_count_scoped_to_name():
    p = RetryPolicy(base_delay=0.0)
    p.execute("a", lambda: "ok")
    p.execute("a", lambda: "ok")
    p.execute("b", lambda: "ok")
    assert p.count("a") == 2
    assert p.count("b") == 1


# ── AttemptRecord shape ─────────────────────────────────────────────────────

def test_attempt_record_to_dict_has_required_keys():
    p = RetryPolicy(base_delay=0.0)
    p.execute("svc", lambda: "ok")
    rec = p.get_history("svc")[0]
    for k in ("name", "attempt", "outcome", "elapsed", "error", "ts"):
        assert k in rec


def test_elapsed_is_positive_float():
    p = RetryPolicy(base_delay=0.0)
    p.execute("svc", lambda: "ok")
    rec = p.get_history("svc")[0]
    assert isinstance(rec["elapsed"], float)
    assert rec["elapsed"] >= 0.0


# ── thread safety ────────────────────────────────────────────────────────────

def test_thread_safety_20_concurrent_executes():
    p = RetryPolicy(max_attempts=1, base_delay=0.0, jitter=0.0)
    errors: list[Exception] = []

    def worker(i: int):
        try:
            p.execute("svc", lambda: f"r{i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert p.count("svc") == 20
