"""Phase 82 — unit tests for UnionFind (disjoint-set forest)."""
from __future__ import annotations

import random
import threading
import time

import pytest

from pradyos.core.unionfind import UnionFind


# ── construction ──────────────────────────────────────────────────────────────

def test_construction_size():
    assert UnionFind(10).size == 10


def test_initial_component_count():
    assert UnionFind(10).component_count() == 10


def test_invalid_size_zero_raises():
    with pytest.raises(ValueError):
        UnionFind(0)


def test_invalid_size_negative_or_non_int_raises():
    for bad in (-3, 2.5):
        with pytest.raises(ValueError):
            UnionFind(bad)


# ── union / find / connected ──────────────────────────────────────────────────

def test_union_distinct_returns_true():
    assert UnionFind(5).union(1, 2) is True


def test_union_already_connected_returns_false():
    u = UnionFind(5)
    u.union(1, 2)
    assert u.union(1, 2) is False


def test_self_union_is_noop():
    u = UnionFind(5)
    before = u.component_count()
    assert u.union(3, 3) is False
    assert u.component_count() == before


def test_find_singleton_is_self():
    assert UnionFind(5).find(4) == 4


def test_connected_after_union():
    u = UnionFind(5)
    u.union(1, 2)
    assert u.connected(1, 2) is True


def test_not_connected_initially():
    assert UnionFind(5).connected(1, 2) is False


def test_transitivity():
    u = UnionFind(5)
    u.union(1, 2)
    u.union(2, 3)
    assert u.connected(1, 3) is True
    assert u.find(1) == u.find(3)


def test_connected_elements_share_root():
    u = UnionFind(6)
    u.union(1, 2); u.union(3, 4); u.union(1, 4)
    root = u.find(1)
    assert all(u.find(x) == root for x in (1, 2, 3, 4))
    assert u.find(5) != root


# ── component count / size ────────────────────────────────────────────────────

def test_component_count_decrements_per_union():
    u = UnionFind(5)
    u.union(1, 2)
    assert u.component_count() == 4
    u.union(3, 4)
    assert u.component_count() == 3


def test_redundant_union_does_not_decrement():
    u = UnionFind(5)
    u.union(1, 2)
    u.union(1, 2)
    assert u.component_count() == 4


def test_component_size_grows():
    u = UnionFind(5)
    assert u.component_size(1) == 1
    u.union(1, 2)
    assert u.component_size(1) == 2
    u.union(2, 3)
    assert u.component_size(1) == 3


def test_union_all_into_one():
    u = UnionFind(100)
    for i in range(2, 101):
        u.union(1, i)
    assert u.component_count() == 1
    assert u.component_size(50) == 100


# ── reset ─────────────────────────────────────────────────────────────────────

def test_reset_restores_isolated_components():
    u = UnionFind(10)
    u.union(1, 2); u.union(3, 4)
    u.reset()
    assert u.component_count() == 10


def test_reset_breaks_connections():
    u = UnionFind(5)
    u.union(1, 2)
    u.reset()
    assert u.connected(1, 2) is False
    assert u.component_size(1) == 1


# ── correctness vs a reference DSU ────────────────────────────────────────────

def test_correctness_vs_reference():
    n = 200
    u = UnionFind(n)
    parent = list(range(n + 1))

    def root(x):
        while parent[x] != x:
            x = parent[x]
        return x

    rng = random.Random(7)
    for _ in range(500):
        a = rng.randint(1, n)
        b = rng.randint(1, n)
        u.union(a, b)
        parent[root(a)] = root(b)

    for a in (1, 50, 100, 200):
        for b in range(1, n + 1):
            assert u.connected(a, b) == (root(a) == root(b))


def test_path_compression_preserves_correctness():
    n = 100
    u = UnionFind(n)
    for i in range(2, n + 1):
        u.union(1, i)        # a long chain that compression should flatten
    for i in range(1, n + 1):
        u.find(i)            # trigger path halving across the forest
    assert all(u.connected(1, i) for i in range(1, n + 1))
    assert u.component_count() == 1


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(UnionFind(5).stats()) == {"size", "components", "largest_component"}


def test_stats_tracks_components_and_largest():
    u = UnionFind(10)
    u.union(1, 2); u.union(2, 3); u.union(3, 4)
    stats = u.stats()
    assert stats["components"] == 7
    assert stats["largest_component"] == 4


# ── boundaries / errors ───────────────────────────────────────────────────────

def test_boundary_first_and_last():
    u = UnionFind(5)
    u.union(1, 5)
    assert u.connected(1, 5) is True
    assert u.component_size(1) == 2


def test_find_out_of_bounds_raises():
    u = UnionFind(10)
    for bad in (0, 11):
        with pytest.raises(ValueError):
            u.find(bad)


def test_union_out_of_bounds_raises():
    u = UnionFind(10)
    with pytest.raises(ValueError):
        u.union(0, 1)
    with pytest.raises(ValueError):
        u.union(1, 11)


def test_connected_out_of_bounds_raises():
    with pytest.raises(ValueError):
        UnionFind(10).connected(1, 99)


def test_component_size_out_of_bounds_raises():
    with pytest.raises(ValueError):
        UnionFind(10).component_size(0)


def test_non_integer_element_raises():
    with pytest.raises(ValueError):
        UnionFind(10).find(1.5)


# ── O(alpha(n)) performance ───────────────────────────────────────────────────

def test_near_constant_time_performance():
    n = 1_000_000
    u = UnionFind(n)
    rng = random.Random(1)
    start = time.monotonic()
    for _ in range(100_000):
        u.union(rng.randint(1, n), rng.randint(1, n))
        u.find(rng.randint(1, n))
    elapsed = time.monotonic() - start
    # union-by-rank + path halving → near-O(alpha(n)); 100k ops on n=1M is fast.
    assert elapsed < 1.0
    assert u.component_count() <= n


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_unions_are_thread_safe():
    u = UnionFind(1000)
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            # each thread chains its own disjoint block of 100 elements
            for i in range(base + 1, base + 100):
                u.union(base + 1, i + 1)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(0, 1000, 100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # 10 disjoint blocks, each fully merged → exactly 10 components
    assert u.component_count() == 10
    assert all(u.component_size(b + 1) == 100 for b in range(0, 1000, 100))
