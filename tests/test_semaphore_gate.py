"""Phase 57C — 20 tests for pradyos.core.semaphore_gate.SemaphoreGate."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.semaphore_gate import (
    SemaphoreGate,
    SemaphoreNotFoundError,
    SemaphoreStats,
    SemaphoreTimeoutError,
)


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty_list_names():
    g = SemaphoreGate()
    assert g.list_names() == []


# ── create ────────────────────────────────────────────────────────────────────

def test_create_returns_stats_with_correct_capacity():
    g = SemaphoreGate()
    stats = g.create("svc", capacity=3)
    assert isinstance(stats, SemaphoreStats)
    assert stats.capacity == 3
    assert stats.available == 3


def test_create_idempotent_same_capacity():
    g = SemaphoreGate()
    g.create("svc", capacity=2)
    stats = g.create("svc", capacity=2)
    assert stats.capacity == 2


def test_create_capacity_mismatch_raises():
    g = SemaphoreGate()
    g.create("svc", capacity=2)
    with pytest.raises(ValueError, match="cannot redefine"):
        g.create("svc", capacity=5)


# ── acquire ───────────────────────────────────────────────────────────────────

def test_acquire_true_when_slot_available():
    g = SemaphoreGate()
    g.create("svc", capacity=1)
    assert g.acquire("svc", timeout=0) is True


def test_acquire_increments_acquired_total():
    g = SemaphoreGate()
    g.create("svc", capacity=2)
    g.acquire("svc", timeout=0)
    g.acquire("svc", timeout=0)
    assert g.get_stats("svc").acquired_total == 2


def test_acquire_timeout_zero_returns_false_when_no_slots():
    g = SemaphoreGate()
    g.create("svc", capacity=1)
    g.acquire("svc", timeout=0)  # take the only slot
    assert g.acquire("svc", timeout=0) is False


def test_acquire_false_increments_timeout_total():
    g = SemaphoreGate()
    g.create("svc", capacity=1)
    g.acquire("svc", timeout=0)
    g.acquire("svc", timeout=0)  # fails
    assert g.get_stats("svc").timeout_total == 1


# ── release ───────────────────────────────────────────────────────────────────

def test_release_increments_released_total():
    g = SemaphoreGate()
    g.create("svc", capacity=1)
    g.acquire("svc", timeout=0)
    g.release("svc")
    assert g.get_stats("svc").released_total == 1


def test_release_makes_slot_available_again():
    g = SemaphoreGate()
    g.create("svc", capacity=1)
    g.acquire("svc", timeout=0)
    assert g.acquire("svc", timeout=0) is False  # full
    g.release("svc")
    assert g.acquire("svc", timeout=0) is True   # slot back


# ── get_stats ────────────────────────────────────────────────────────────────

def test_get_stats_returns_semaphore_stats():
    g = SemaphoreGate()
    g.create("svc", capacity=4)
    stats = g.get_stats("svc")
    assert isinstance(stats, SemaphoreStats)


def test_get_stats_available_reflects_acquired():
    g = SemaphoreGate()
    g.create("svc", capacity=3)
    g.acquire("svc", timeout=0)
    g.acquire("svc", timeout=0)
    assert g.get_stats("svc").available == 1


def test_get_stats_unknown_raises_not_found():
    g = SemaphoreGate()
    with pytest.raises(SemaphoreNotFoundError):
        g.get_stats("phantom")


# ── unknown-name handling ────────────────────────────────────────────────────

def test_acquire_unknown_raises_not_found():
    g = SemaphoreGate()
    with pytest.raises(SemaphoreNotFoundError):
        g.acquire("phantom", timeout=0)


def test_release_unknown_raises_not_found():
    g = SemaphoreGate()
    with pytest.raises(SemaphoreNotFoundError):
        g.release("phantom")


# ── list_names / delete ──────────────────────────────────────────────────────

def test_list_names_sorted():
    g = SemaphoreGate()
    g.create("zzz")
    g.create("aaa")
    g.create("mmm")
    assert g.list_names() == ["aaa", "mmm", "zzz"]


def test_delete_returns_true_removes():
    g = SemaphoreGate()
    g.create("svc")
    assert g.delete("svc") is True
    assert g.list_names() == []


def test_delete_unknown_returns_false():
    g = SemaphoreGate()
    assert g.delete("phantom") is False


# ── exception type ───────────────────────────────────────────────────────────

def test_semaphore_timeout_error_is_runtime_error():
    assert issubclass(SemaphoreTimeoutError, RuntimeError)


# ── concurrency ──────────────────────────────────────────────────────────────

def test_thread_safety_10_acquire_release_on_capacity_5():
    g = SemaphoreGate()
    g.create("svc", capacity=5)
    errors: list[Exception] = []

    def worker():
        try:
            ok = g.acquire("svc", timeout=2.0)
            assert ok is True
            time.sleep(0.005)
            g.release("svc")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    stats = g.get_stats("svc")
    assert stats.acquired_total == 10
    assert stats.released_total == 10
    assert stats.available == 5  # back to full
