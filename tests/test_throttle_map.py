"""Phase 59C — 20 tests for pradyos.core.throttle_map.ThrottleMap."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.throttle_map import ThrottleMap


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty():
    t = ThrottleMap()
    assert t._keys == {}
    assert t.list_keys() == []


# ── allow basics ──────────────────────────────────────────────────────────────

def test_allow_returns_true_under_limit():
    t = ThrottleMap()
    assert t.allow("k", limit=5, window=10) is True
    assert t.allow("k", limit=5, window=10) is True


def test_allow_returns_false_when_limit_exceeded():
    t = ThrottleMap()
    for _ in range(3):
        assert t.allow("k", limit=3, window=10) is True
    assert t.allow("k", limit=3, window=10) is False


def test_allow_resets_after_window_expires():
    t = ThrottleMap()
    # 2 allowed in a 0.05s window
    assert t.allow("k", 2, 0.05) is True
    assert t.allow("k", 2, 0.05) is True
    assert t.allow("k", 2, 0.05) is False
    time.sleep(0.07)  # window has fully elapsed
    assert t.allow("k", 2, 0.05) is True


def test_allow_auto_creates_key_on_first_call():
    t = ThrottleMap()
    t.allow("brand_new", 5, 1.0)
    assert "brand_new" in t._keys


# ── reset ─────────────────────────────────────────────────────────────────────

def test_reset_returns_true_clears_counts():
    t = ThrottleMap()
    t.allow("k", 1, 10)
    t.allow("k", 1, 10)  # rejected
    assert t.reset("k") is True
    s = t.stats("k", 1, 10)
    assert s["allowed_total"] == 0
    assert s["rejected_total"] == 0
    assert s["calls_in_window"] == 0


def test_reset_returns_false_for_unknown():
    t = ThrottleMap()
    assert t.reset("phantom") is False


def test_allow_works_again_after_reset():
    t = ThrottleMap()
    t.allow("k", 1, 10)
    assert t.allow("k", 1, 10) is False  # over limit
    t.reset("k")
    assert t.allow("k", 1, 10) is True  # accepts again


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_returns_none_for_unknown():
    t = ThrottleMap()
    assert t.stats("phantom", 5, 10) is None


def test_stats_calls_in_window_correct():
    t = ThrottleMap()
    for _ in range(3):
        t.allow("k", 10, 60)
    assert t.stats("k", 10, 60)["calls_in_window"] == 3


def test_stats_allowed_and_rejected_totals():
    t = ThrottleMap()
    for _ in range(2):
        t.allow("k", 2, 60)
    for _ in range(3):
        t.allow("k", 2, 60)  # rejected
    s = t.stats("k", 2, 60)
    assert s["allowed_total"] == 2
    assert s["rejected_total"] == 3


def test_stats_calls_in_window_zero_after_expiry():
    t = ThrottleMap()
    t.allow("k", 10, 0.05)
    t.allow("k", 10, 0.05)
    time.sleep(0.07)
    assert t.stats("k", 10, 0.05)["calls_in_window"] == 0


# ── list_keys / delete ───────────────────────────────────────────────────────

def test_list_keys_sorted():
    t = ThrottleMap()
    t.allow("zzz", 1, 10)
    t.allow("aaa", 1, 10)
    t.allow("mmm", 1, 10)
    assert t.list_keys() == ["aaa", "mmm", "zzz"]


def test_list_keys_includes_after_first_allow():
    t = ThrottleMap()
    t.allow("k", 1, 10)
    assert "k" in t.list_keys()


def test_delete_returns_true_removes_key():
    t = ThrottleMap()
    t.allow("k", 1, 10)
    assert t.delete("k") is True
    assert "k" not in t._keys


def test_delete_returns_false_unknown():
    t = ThrottleMap()
    assert t.delete("phantom") is False


def test_stats_after_delete_returns_none():
    t = ThrottleMap()
    t.allow("k", 1, 10)
    t.delete("k")
    assert t.stats("k", 1, 10) is None


# ── independence between keys ────────────────────────────────────────────────

def test_multiple_keys_are_independent():
    t = ThrottleMap()
    # Saturate key a
    t.allow("a", 1, 10)
    assert t.allow("a", 1, 10) is False
    # Key b is fresh
    assert t.allow("b", 1, 10) is True


# ── concurrency ──────────────────────────────────────────────────────────────

def test_thread_safety_50_concurrent_allows_exactly_25_allowed():
    t = ThrottleMap()
    LIMIT = 25
    WINDOW = 60
    allowed = [0]
    rejected = [0]
    lock = threading.Lock()

    def worker():
        ok = t.allow("k", LIMIT, WINDOW)
        with lock:
            if ok:
                allowed[0] += 1
            else:
                rejected[0] += 1

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert allowed[0] == LIMIT
    assert rejected[0] == 50 - LIMIT


def test_cumulative_allowed_plus_rejected_equals_total_calls():
    t = ThrottleMap()
    LIMIT = 5
    WINDOW = 60
    for _ in range(15):
        t.allow("k", LIMIT, WINDOW)
    s = t.stats("k", LIMIT, WINDOW)
    assert s["allowed_total"] + s["rejected_total"] == 15
