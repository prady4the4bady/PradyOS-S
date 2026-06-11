"""Phase 52C — 20 tests for pradyos.core.distributed_lock.LockManager."""
from __future__ import annotations

import time

import pytest

from pradyos.core.distributed_lock import DistributedLock, LockManager


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty():
    m = LockManager()
    assert m._locks == {}


# ── acquire ───────────────────────────────────────────────────────────────────

def test_acquire_returns_distributedlock():
    m = LockManager()
    lk = m.acquire("res", "h1")
    assert isinstance(lk, DistributedLock)


def test_acquire_first_call_correct_fields():
    m = LockManager()
    lk = m.acquire("res", "h1", ttl=60.0)
    assert lk.name == "res"
    assert lk.holder_id == "h1"
    assert lk.ttl_seconds == 60.0
    assert lk.expires_at > lk.acquired_at


def test_is_locked_true_after_acquire():
    m = LockManager()
    m.acquire("res", "h1")
    assert m.is_locked("res") is True


def test_acquire_second_caller_returns_none():
    m = LockManager()
    m.acquire("res", "h1")
    assert m.acquire("res", "h2") is None


def test_acquire_same_holder_replaces():
    m = LockManager()
    lk1 = m.acquire("res", "h1", ttl=1.0)
    time.sleep(0.005)
    lk2 = m.acquire("res", "h1", ttl=60.0)
    assert lk2 is not None
    assert lk2.holder_id == "h1"
    assert lk2.expires_at > lk1.expires_at


def test_acquire_expired_lock_can_be_taken_by_new_holder():
    m = LockManager()
    m.acquire("res", "h1", ttl=0.001)
    time.sleep(0.01)
    lk = m.acquire("res", "h2")
    assert lk is not None
    assert lk.holder_id == "h2"


# ── release ───────────────────────────────────────────────────────────────────

def test_release_returns_true_unlocks():
    m = LockManager()
    m.acquire("res", "h1")
    assert m.release("res", "h1") is True
    assert m.is_locked("res") is False


def test_release_wrong_holder_returns_false():
    m = LockManager()
    m.acquire("res", "h1")
    assert m.release("res", "h2") is False
    assert m.is_locked("res") is True  # still locked


def test_release_unknown_returns_false():
    m = LockManager()
    assert m.release("phantom", "h1") is False


# ── refresh ───────────────────────────────────────────────────────────────────

def test_refresh_returns_true_extends_expires_at():
    m = LockManager()
    lk = m.acquire("res", "h1", ttl=1.0)
    original_exp = lk.expires_at
    time.sleep(0.005)
    assert m.refresh("res", "h1", ttl=60.0) is True
    refreshed = m._locks["res"]
    assert refreshed.expires_at > original_exp


def test_refresh_wrong_holder_returns_false():
    m = LockManager()
    m.acquire("res", "h1")
    assert m.refresh("res", "h2") is False


def test_refresh_expired_returns_false():
    m = LockManager()
    m.acquire("res", "h1", ttl=0.001)
    time.sleep(0.01)
    assert m.refresh("res", "h1") is False


# ── is_locked / list_locks ───────────────────────────────────────────────────

def test_is_locked_false_for_unknown():
    m = LockManager()
    assert m.is_locked("phantom") is False


def test_is_locked_false_after_release():
    m = LockManager()
    m.acquire("res", "h1")
    m.release("res", "h1")
    assert m.is_locked("res") is False


def test_list_locks_excludes_expired():
    m = LockManager()
    m.acquire("alive", "h1", ttl=60.0)
    m.acquire("dying", "h2", ttl=0.001)
    time.sleep(0.01)
    names = [lk["name"] for lk in m.list_locks()]
    assert names == ["alive"]


def test_list_locks_sorted_by_acquired_at():
    m = LockManager()
    m.acquire("a", "h1", ttl=60.0)
    time.sleep(0.001)
    m.acquire("b", "h1", ttl=60.0)
    time.sleep(0.001)
    m.acquire("c", "h1", ttl=60.0)
    names = [lk["name"] for lk in m.list_locks()]
    assert names == ["a", "b", "c"]


# ── expire_stale / count ─────────────────────────────────────────────────────

def test_expire_stale_removes_and_returns_count():
    m = LockManager()
    m.acquire("x", "h1", ttl=0.001)
    m.acquire("y", "h1", ttl=0.001)
    m.acquire("z", "h1", ttl=60.0)
    time.sleep(0.01)
    assert m.expire_stale() == 2
    assert "z" in m._locks
    assert "x" not in m._locks
    assert "y" not in m._locks


def test_count_excludes_expired_by_default():
    m = LockManager()
    m.acquire("alive", "h1", ttl=60.0)
    m.acquire("dying", "h2", ttl=0.001)
    time.sleep(0.01)
    assert m.count() == 1


def test_count_include_expired_true_counts_all():
    m = LockManager()
    m.acquire("alive", "h1", ttl=60.0)
    m.acquire("dying", "h2", ttl=0.001)
    time.sleep(0.01)
    assert m.count(include_expired=True) == 2
