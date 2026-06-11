"""Phase 161 — unit tests for BinaryLifting (pradyos/core/binary_lifting.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.binary_lifting import BinaryLifting, BinaryLiftingError


def _chain(par, v):
    out = []
    while v != -1:
        out.append(v); v = par[v]
    return out


def _ndepth(par, v):
    return len(_chain(par, v)) - 1


def _nkth(par, v, k):
    c = _chain(par, v)
    return c[k] if k < len(c) else None


def _nlca(par, u, v):
    su = set(_chain(par, u))
    for x in _chain(par, v):
        if x in su:
            return x
    return None


def _nisanc(par, u, v):
    return u in _chain(par, v)


def _rand_forest(rng, n):
    par = [-1] * n
    for v in range(n):
        if v == 0 or rng.random() < 0.2:
            par[v] = -1
        else:
            par[v] = rng.randrange(v)
    return par


# ── differential vs naive ancestor-walk (centerpieces) ────────────────────────────────────

def test_lca_differential():
    rng = random.Random(1)
    for _ in range(60):
        n = rng.randint(1, 80)
        par = _rand_forest(rng, n)
        bl = BinaryLifting(par)
        for _ in range(8):
            u = rng.randrange(n); v = rng.randrange(n)
            assert bl.lca(u, v) == _nlca(par, u, v)


def test_kth_ancestor_differential():
    rng = random.Random(2)
    for _ in range(60):
        n = rng.randint(1, 80)
        par = _rand_forest(rng, n)
        bl = BinaryLifting(par)
        for _ in range(8):
            v = rng.randrange(n); k = rng.randint(0, n)
            assert bl.kth_ancestor(v, k) == _nkth(par, v, k)


def test_is_ancestor_differential():
    rng = random.Random(3)
    for _ in range(60):
        n = rng.randint(1, 80)
        par = _rand_forest(rng, n)
        bl = BinaryLifting(par)
        for _ in range(8):
            u = rng.randrange(n); v = rng.randrange(n)
            assert bl.is_ancestor(u, v) == _nisanc(par, u, v)


def test_depth_differential():
    rng = random.Random(4)
    par = _rand_forest(rng, 200)
    bl = BinaryLifting(par)
    assert all(bl.depth(v) == _ndepth(par, v) for v in range(200))


def test_large_binary_tree_lca():
    rng = random.Random(5)
    n = 4000
    par = [-1] + [(i - 1) // 2 for i in range(1, n)]
    bl = BinaryLifting(par)
    for _ in range(200):
        u = rng.randrange(n); v = rng.randrange(n)
        assert bl.lca(u, v) == _nlca(par, u, v)


# ── structured trees ─────────────────────────────────────────────────────────────────────

def test_chain():
    n = 1000
    par = [-1] + [i - 1 for i in range(1, n)]
    bl = BinaryLifting(par)
    assert bl.lca(999, 500) == 500 and bl.lca(300, 700) == 300
    assert bl.kth_ancestor(999, 1) == 998 and bl.kth_ancestor(999, 999) == 0
    assert bl.kth_ancestor(999, 1000) is None
    assert bl.depth(999) == 999 and bl.is_ancestor(0, 999) and not bl.is_ancestor(999, 500)


def test_star():
    n = 500
    par = [-1] + [0] * (n - 1)
    bl = BinaryLifting(par)
    assert bl.lca(5, 300) == 0 and bl.lca(0, 250) == 0
    assert all(bl.depth(v) == 1 for v in range(1, n)) and bl.depth(0) == 0


def test_forest_within_and_across():
    par = [-1, 0, 0, -1, 3, 3]
    bl = BinaryLifting(par)
    assert bl.lca(1, 2) == 0 and bl.lca(4, 5) == 3
    assert bl.lca(1, 4) is None and bl.lca(2, 5) is None
    assert bl.stats()["num_roots"] == 2


def test_self_lca():
    bl = BinaryLifting([-1, 0, 1, 2])
    assert bl.lca(2, 2) == 2


def test_reflexive_is_ancestor():
    bl = BinaryLifting([-1, 0, 1, 2])
    assert bl.is_ancestor(2, 2) is True


def test_lca_with_own_ancestor():
    bl = BinaryLifting([-1, 0, 1, 2])
    assert bl.lca(3, 1) == 1 and bl.lca(1, 3) == 1


def test_kth_zero_is_self():
    bl = BinaryLifting([-1, 0, 1, 2])
    assert bl.kth_ancestor(3, 0) == 3


def test_single_node():
    bl = BinaryLifting([-1])
    assert bl.depth(0) == 0 and bl.lca(0, 0) == 0
    assert bl.kth_ancestor(0, 1) is None and bl.is_ancestor(0, 0)


def test_kth_exceeds_depth_none():
    bl = BinaryLifting([-1, 0, 1])
    assert bl.kth_ancestor(2, 2) == 0 and bl.kth_ancestor(2, 3) is None


def test_depth_root_zero():
    bl = BinaryLifting([-1, 0, 0])
    assert bl.depth(0) == 0


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_build_self_parent_raises():
    with pytest.raises(BinaryLiftingError):
        BinaryLifting([0, 1])                        # node 0 is its own parent


def test_build_cycle_raises():
    with pytest.raises(BinaryLiftingError):
        BinaryLifting([1, 0])                        # 0 <-> 1 cycle


def test_build_out_of_range_raises():
    with pytest.raises(BinaryLiftingError):
        BinaryLifting([5])


def test_build_non_int_raises():
    with pytest.raises(BinaryLiftingError):
        BinaryLifting([-1, "x"])


def test_lca_node_out_of_range_raises():
    with pytest.raises(BinaryLiftingError):
        BinaryLifting([-1, 0]).lca(0, 9)


def test_kth_negative_raises():
    with pytest.raises(BinaryLiftingError):
        BinaryLifting([-1, 0]).kth_ancestor(0, -1)


def test_depth_non_int_raises():
    with pytest.raises(BinaryLiftingError):
        BinaryLifting([-1, 0]).depth(0.5)


def test_error_stores_detail():
    err = BinaryLiftingError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── build / reset / introspection ─────────────────────────────────────────────────────────

def test_build_replaces():
    bl = BinaryLifting([-1, 0, 1])
    bl.build([-1, 0, 0, 0])
    assert bl.size == 4 and bl.lca(1, 2) == 0 and bl.lca(3, 1) == 0


def test_reset_clears():
    bl = BinaryLifting([-1, 0, 1])
    bl.reset()
    assert bl.is_empty() and bl.size == 0


def test_empty():
    assert BinaryLifting([]).is_empty() and len(BinaryLifting([])) == 0


def test_size_len_levels():
    bl = BinaryLifting([-1, 0, 1, 2, 3])
    assert bl.size == 5 and len(bl) == 5 and bl.levels >= 1


def test_stats_keys():
    assert set(BinaryLifting([-1, 0]).stats()) == {"size", "levels", "max_depth", "num_roots"}


def test_stats_values():
    bl = BinaryLifting([-1, 0, 1, 2])               # chain depth 3
    s = bl.stats()
    assert s["size"] == 4 and s["max_depth"] == 3 and s["num_roots"] == 1


def test_deterministic():
    def build():
        return BinaryLifting([-1, 0, 1, 1, 2, 2]).lca(4, 5)
    assert build() == build()


# ── concurrency (read-only queries on a built structure) ──────────────────────────────────

def test_concurrent_queries():
    rng = random.Random(6)
    n = 2000
    par = [-1] + [rng.randrange(i) for i in range(1, n)]
    bl = BinaryLifting(par)
    errors = []
    results = []

    def worker():
        try:
            ok = all(bl.lca(u, v) == _nlca(par, u, v)
                     for u, v in [(rng.randrange(n), rng.randrange(n)) for _ in range(50)])
            results.append(ok)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
