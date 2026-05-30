"""Phase 84 — unit tests for SovereignLRUCache (LRU cache with TTL)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.lru_cache import CacheMissError, SovereignLRUCache


class _Clock:
    """A controllable monotonic clock for deterministic TTL tests."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


# ── construction ──────────────────────────────────────────────────────────────

def test_construction_capacity():
    assert SovereignLRUCache(5).capacity == 5


def test_invalid_capacity_raises():
    for bad in (0, -1, 2.5):
        with pytest.raises(ValueError):
            SovereignLRUCache(bad)


# ── put / get ─────────────────────────────────────────────────────────────────

def test_put_get_round_trip():
    c = SovereignLRUCache(3)
    c.put("a", 1)
    assert c.get("a") == 1


def test_get_absent_raises_cache_miss():
    with pytest.raises(CacheMissError):
        SovereignLRUCache(3).get("ghost")


def test_cache_miss_carries_key():
    try:
        SovereignLRUCache(3).get("ghost")
    except CacheMissError as exc:
        assert exc.key == "ghost"
        assert "ghost" in str(exc)
    else:  # pragma: no cover
        pytest.fail("expected CacheMissError")


def test_put_updates_existing_value():
    c = SovereignLRUCache(3)
    c.put("a", 1)
    c.put("a", 2)
    assert c.get("a") == 2
    assert len(c) == 1


def test_len_tracks_size():
    c = SovereignLRUCache(5)
    c.put("a", 1); c.put("b", 2)
    assert len(c) == 2


# ── LRU eviction ──────────────────────────────────────────────────────────────

def test_eviction_when_over_capacity():
    c = SovereignLRUCache(2)
    c.put("a", 1); c.put("b", 2); c.put("c", 3)   # 'a' is LRU → evicted
    assert not c.contains("a")
    assert c.contains("b") and c.contains("c")


def test_get_refreshes_recency():
    c = SovereignLRUCache(2)
    c.put("x", 1); c.put("y", 2)
    c.get("x")                  # x now most-recent
    c.put("z", 3)               # y is LRU → evicted
    assert c.contains("x") and c.contains("z")
    assert not c.contains("y")


def test_eviction_counter():
    c = SovereignLRUCache(1)
    c.put("a", 1); c.put("b", 2)
    assert c.stats()["evictions"] == 1


def test_capacity_one():
    c = SovereignLRUCache(1)
    c.put("a", 1); c.put("b", 2)
    assert len(c) == 1
    assert c.get("b") == 2
    assert not c.contains("a")


# ── peek ──────────────────────────────────────────────────────────────────────

def test_peek_does_not_refresh_recency():
    c = SovereignLRUCache(2)
    c.put("a", 1); c.put("b", 2)
    c.peek("a")                 # peek must NOT save 'a' from eviction
    c.put("c", 3)
    assert not c.contains("a")


def test_peek_absent_raises():
    with pytest.raises(CacheMissError):
        SovereignLRUCache(2).peek("nope")


def test_peek_does_not_count_hit():
    c = SovereignLRUCache(2)
    c.put("a", 1)
    c.peek("a")
    assert c.stats()["hits"] == 0


# ── TTL ───────────────────────────────────────────────────────────────────────

def test_ttl_value_before_expiry():
    clk = _Clock()
    c = SovereignLRUCache(5, time_fn=clk)
    c.put("k", "v", ttl=10)
    clk.t = 9
    assert c.get("k") == "v"


def test_ttl_expires():
    clk = _Clock()
    c = SovereignLRUCache(5, time_fn=clk)
    c.put("k", "v", ttl=10)
    clk.t = 11
    with pytest.raises(CacheMissError):
        c.get("k")


def test_ttl_expiry_purges_and_counts():
    clk = _Clock()
    c = SovereignLRUCache(5, time_fn=clk)
    c.put("k", "v", ttl=5)
    clk.t = 6
    assert not c.contains("k")
    assert len(c) == 0
    assert c.stats()["expirations"] >= 1


def test_ttl_none_never_expires():
    clk = _Clock()
    c = SovereignLRUCache(5, time_fn=clk)
    c.put("k", "v")
    clk.t = 10 ** 9
    assert c.get("k") == "v"


def test_invalid_ttl_raises():
    for bad in (0, -5):
        with pytest.raises(ValueError):
            SovereignLRUCache(2).put("k", 1, ttl=bad)


# ── delete / resize ───────────────────────────────────────────────────────────

def test_delete_present_and_absent():
    c = SovereignLRUCache(3)
    c.put("a", 1)
    assert c.delete("a") is True
    assert c.delete("a") is False


def test_delete_then_get_misses():
    c = SovereignLRUCache(3)
    c.put("a", 1)
    c.delete("a")
    with pytest.raises(CacheMissError):
        c.get("a")


def test_resize_smaller_evicts_lru():
    c = SovereignLRUCache(4)
    for k, v in zip("abcd", range(4)):
        c.put(k, v)
    c.resize(2)
    assert len(c) == 2
    # the two most-recently-inserted survive
    assert c.contains("c") and c.contains("d")
    assert not c.contains("a")


def test_resize_larger_keeps_all():
    c = SovereignLRUCache(2)
    c.put("a", 1); c.put("b", 2)
    c.resize(10)
    assert c.capacity == 10
    assert len(c) == 2


def test_resize_invalid_raises():
    with pytest.raises(ValueError):
        SovereignLRUCache(3).resize(0)


# ── contains / clear ──────────────────────────────────────────────────────────

def test_contains_true_false():
    c = SovereignLRUCache(2)
    c.put("a", 1)
    assert c.contains("a") is True
    assert c.contains("b") is False


def test_clear_resets_data_and_stats():
    c = SovereignLRUCache(2)
    c.put("a", 1); c.get("a")
    c.clear()
    assert len(c) == 0
    assert c.stats()["hits"] == 0


# ── snapshot / stats / to_dict ────────────────────────────────────────────────

def test_snapshot_ordered_most_recent_first():
    c = SovereignLRUCache(3)
    c.put("a", 1); c.put("b", 2); c.put("c", 3)
    assert [k for k, _ in c.snapshot()] == ["c", "b", "a"]


def test_snapshot_reflects_access_order():
    c = SovereignLRUCache(3)
    c.put("a", 1); c.put("b", 2); c.put("c", 3)
    c.get("a")                       # a becomes most-recent
    assert [k for k, _ in c.snapshot()][0] == "a"


def test_stats_keys():
    stats = SovereignLRUCache(2).stats()
    assert set(stats) == {"capacity", "size", "hits", "misses",
                          "hit_rate", "evictions", "expirations"}


def test_hit_rate_computation():
    c = SovereignLRUCache(2)
    c.put("a", 1)
    c.get("a")               # hit
    with pytest.raises(CacheMissError):
        c.get("b")           # miss
    assert c.stats()["hit_rate"] == 0.5


def test_to_dict_structure():
    c = SovereignLRUCache(2)
    c.put("a", 1)
    d = c.to_dict()
    assert set(d) == {"capacity", "size", "entries"}
    assert d["entries"] == [["a", 1]]


# ── input validation ──────────────────────────────────────────────────────────

def test_non_string_key_raises():
    c = SovereignLRUCache(2)
    for op in (lambda: c.get(5), lambda: c.put(5, 1), lambda: c.delete(5), lambda: c.peek(5)):
        with pytest.raises(ValueError):
            op()


def test_empty_key_put_raises():
    with pytest.raises(ValueError):
        SovereignLRUCache(2).put("", 1)


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_puts_and_gets_are_thread_safe():
    c = SovereignLRUCache(2000)
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            for i in range(100):
                c.put(f"k-{base}-{i}", base * 1000 + i)
                c.get(f"k-{base}-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(c) == 1000
    assert c.get("k-5-50") == 5050
