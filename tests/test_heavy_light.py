"""Phase 165 — unit tests for HeavyLight (pradyos/core/heavy_light.py)."""
from __future__ import annotations

import random
import threading
from collections import deque

import pytest

from pradyos.core.heavy_light import HeavyLight, HeavyLightError


def _ndepth(par):
    n = len(par); dep = [0] * n
    for v in range(n):
        d = 0; x = v
        while par[x] != -1:
            x = par[x]; d += 1
        dep[v] = d
    return dep


def _path_nodes(par, dep, u, v):
    pu = []; pv = []
    a, b = u, v
    while dep[a] > dep[b]:
        pu.append(a); a = par[a]
    while dep[b] > dep[a]:
        pv.append(b); b = par[b]
    while a != b:
        pu.append(a); pv.append(b); a = par[a]; b = par[b]
    return pu + [a] + pv[::-1]


def _subtree_nodes(par, v):
    n = len(par); ch = [[] for _ in range(n)]
    for x in range(n):
        if par[x] != -1:
            ch[par[x]].append(x)
    out = []; dq = deque([v])
    while dq:
        x = dq.popleft(); out.append(x)
        for c in ch[x]:
            dq.append(c)
    return out


def _rand_tree(rng, n):
    par = [-1] * n
    for v in range(1, n):
        par[v] = rng.randrange(v)
    return par


# ── differential vs naive (centerpieces) ─────────────────────────────────────────────────

def test_path_and_subtree_differential():
    rng = random.Random(1)
    for _ in range(40):
        n = rng.randint(1, 80); par = _rand_tree(rng, n)
        vals = [rng.randint(-50, 50) for _ in range(n)]
        dep = _ndepth(par)
        hl = HeavyLight(par, vals)
        for _ in range(n * 3):
            op = rng.random()
            if op < 0.25:
                node = rng.randrange(n); nv = rng.randint(-50, 50); vals[node] = nv; hl.update(node, nv)
            elif op < 0.55:
                u = rng.randrange(n); v = rng.randrange(n)
                assert hl.path_sum(u, v) == sum(vals[x] for x in _path_nodes(par, dep, u, v))
            elif op < 0.8:
                u = rng.randrange(n); v = rng.randrange(n)
                assert hl.path_max(u, v) == max(vals[x] for x in _path_nodes(par, dep, u, v))
            else:
                v = rng.randrange(n)
                assert hl.subtree_sum(v) == sum(vals[x] for x in _subtree_nodes(par, v))


def test_balanced_binary_tree():
    rng = random.Random(2)
    n = 2000
    par = [-1] + [(i - 1) // 2 for i in range(1, n)]
    vals = [rng.randint(0, 100) for _ in range(n)]
    dep = _ndepth(par)
    hl = HeavyLight(par, vals)
    for _ in range(100):
        u = rng.randrange(n); v = rng.randrange(n)
        assert hl.path_sum(u, v) == sum(vals[x] for x in _path_nodes(par, dep, u, v))
        assert hl.path_max(u, v) == max(vals[x] for x in _path_nodes(par, dep, u, v))


# ── structured trees ─────────────────────────────────────────────────────────────────────

def test_chain():
    n = 1000
    par = [-1] + [i - 1 for i in range(1, n)]
    vals = list(range(n))
    hl = HeavyLight(par, vals)
    assert hl.path_sum(0, 999) == sum(range(1000)) and hl.path_sum(100, 200) == sum(range(100, 201))
    assert hl.path_max(0, 999) == 999 and hl.subtree_sum(500) == sum(range(500, 1000))


def test_chain_after_update():
    n = 1000
    par = [-1] + [i - 1 for i in range(1, n)]
    vals = list(range(n))
    hl = HeavyLight(par, vals)
    hl.update(150, 100000)
    assert hl.path_max(100, 200) == 100000
    assert hl.path_sum(0, 999) == sum(range(1000)) - 150 + 100000


def test_star():
    n = 500
    par = [-1] + [0] * (n - 1)
    vals = [1] * n
    hl = HeavyLight(par, vals)
    assert hl.path_sum(5, 300) == 3 and hl.path_max(5, 300) == 1
    assert hl.subtree_sum(0) == 500 and hl.subtree_sum(7) == 1


def test_single_node():
    hl = HeavyLight([-1], [42])
    assert hl.path_sum(0, 0) == 42 and hl.path_max(0, 0) == 42 and hl.subtree_sum(0) == 42
    hl.update(0, 7)
    assert hl.path_sum(0, 0) == 7


def test_self_and_adjacent_path():
    hl = HeavyLight([-1, 0, 1, 2], [1, 2, 3, 4])
    assert hl.path_sum(2, 2) == 3 and hl.path_max(2, 2) == 3
    assert hl.path_sum(0, 1) == 3 and hl.path_sum(1, 3) == 9


def test_path_through_root():
    hl = HeavyLight([-1, 0, 0], [10, 20, 30])
    assert hl.path_sum(1, 2) == 60 and hl.path_max(1, 2) == 30        # 1,0,2


def test_depth():
    hl = HeavyLight([-1, 0, 1, 2], [0, 0, 0, 0])
    assert hl.depth(0) == 0 and hl.depth(3) == 3


def test_default_values_zero():
    hl = HeavyLight([-1, 0, 0])
    assert hl.path_sum(1, 2) == 0 and hl.subtree_sum(0) == 0


def test_floats():
    hl = HeavyLight([-1, 0, 1], [1.5, 2.5, 3.0])
    assert abs(hl.path_sum(0, 2) - 7.0) < 1e-9


# ── validation ────────────────────────────────────────────────────────────────────────────

def test_build_self_parent_raises():
    with pytest.raises(HeavyLightError):
        HeavyLight([0, 1])


def test_build_cycle_raises():
    with pytest.raises(HeavyLightError):
        HeavyLight([1, 0])


def test_build_two_roots_raises():
    with pytest.raises(HeavyLightError):
        HeavyLight([-1, -1])


def test_build_out_of_range_raises():
    with pytest.raises(HeavyLightError):
        HeavyLight([5])


def test_values_length_mismatch_raises():
    with pytest.raises(HeavyLightError):
        HeavyLight([-1, 0], [1, 2, 3])


def test_path_node_out_of_range_raises():
    with pytest.raises(HeavyLightError):
        HeavyLight([-1, 0]).path_sum(0, 9)


def test_update_non_num_raises():
    with pytest.raises(HeavyLightError):
        HeavyLight([-1, 0]).update(0, "x")


def test_error_stores_detail():
    err = HeavyLightError("boom")
    assert err.detail == "boom" and "boom" in str(err)


# ── build / reset / introspection ─────────────────────────────────────────────────────────

def test_build_replaces():
    hl = HeavyLight([-1, 0, 1], [1, 2, 3])
    hl.build([-1, 0, 0, 0], [5, 5, 5, 5])
    assert hl.size == 4 and hl.path_sum(1, 2) == 15 and hl.subtree_sum(0) == 20


def test_reset_clears():
    hl = HeavyLight([-1, 0, 1], [1, 2, 3])
    hl.reset()
    assert hl.is_empty() and hl.size == 0


def test_empty():
    assert HeavyLight([]).is_empty() and len(HeavyLight([])) == 0


def test_size_len():
    hl = HeavyLight([-1, 0, 1, 2, 3], [1, 2, 3, 4, 5])
    assert hl.size == 5 and len(hl) == 5


def test_stats_keys():
    assert set(HeavyLight([-1, 0], [5, 5]).stats()) == {"size", "total", "max", "num_chains"}


def test_stats_values():
    hl = HeavyLight([-1, 0, 0], [10, 20, 30])
    s = hl.stats()
    assert s["size"] == 3 and s["total"] == 60 and s["max"] == 30


def test_deterministic():
    def build():
        return HeavyLight([-1, 0, 0, 1, 1, 2], [1, 2, 3, 4, 5, 6]).path_sum(3, 5)
    assert build() == build()


def test_path_max_after_update():
    hl = HeavyLight([-1, 0, 0, 1, 1, 2], [10, 20, 30, 40, 50, 60])
    hl.update(3, 5)                                       # was 40
    assert hl.path_max(3, 4) == 50 and hl.path_sum(3, 4) == 75      # 5+20+50


def test_subtree_after_update():
    hl = HeavyLight([-1, 0, 0, 1, 1, 2], [10, 20, 30, 40, 50, 60])
    hl.update(4, 0)                                       # subtree(1) = {1,3,4}
    assert hl.subtree_sum(1) == 20 + 40 + 0


def test_two_node_tree():
    hl = HeavyLight([-1, 0], [5, 7])
    assert hl.path_sum(0, 1) == 12 and hl.path_max(0, 1) == 7 and hl.subtree_sum(0) == 12


def test_path_max_through_root():
    hl = HeavyLight([-1, 0, 0], [10, 20, 30])
    assert hl.path_max(1, 2) == 30 and hl.path_sum(1, 2) == 60      # 1,0,2


def test_deep_chain_no_overflow():
    n = 5000
    par = [-1] + [i - 1 for i in range(1, n)]
    hl = HeavyLight(par, [1] * n)                         # iterative build must not overflow
    assert hl.path_sum(0, n - 1) == n and hl.subtree_sum(0) == n


def test_subtree_leaf():
    hl = HeavyLight([-1, 0, 0], [10, 20, 30])
    assert hl.subtree_sum(1) == 20 and hl.subtree_sum(2) == 30


# ── concurrency (read-only path queries on a built tree) ──────────────────────────────────

def test_concurrent_path_queries():
    rng = random.Random(3)
    n = 1500
    par = _rand_tree(rng, n)
    vals = [rng.randint(0, 100) for _ in range(n)]
    dep = _ndepth(par)
    hl = HeavyLight(par, vals)
    errors = []
    results = []

    def worker():
        try:
            ok = all(hl.path_sum(u, v) == sum(vals[x] for x in _path_nodes(par, dep, u, v))
                     for u, v in [(rng.randrange(n), rng.randrange(n)) for _ in range(40)])
            results.append(ok)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and results == [True] * 10
