"""Phase 120 — unit tests for MaglevHash (pradyos/core/maglev.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.maglev import MaglevHash, MaglevError, _is_prime, _next_prime


def _nodes(n):
    return [f"n{i}" for i in range(n)]


# ── prime helpers ────────────────────────────────────────────────────────────────

def test_is_prime():
    assert _is_prime(2) and _is_prime(1009) and not _is_prime(1000) and not _is_prime(1)


def test_next_prime():
    assert _next_prime(1000) == 1009 and _next_prime(1009) == 1009


def test_table_size_bumped_to_prime():
    assert MaglevHash(table_size=1000, seed=0).table_size == 1009


# ── basic correctness ──────────────────────────────────────────────────────────

def test_lookup_deterministic():
    m = MaglevHash(nodes=_nodes(8), table_size=1019, seed=0)
    assert all(m.lookup(f"k{i}") == m.lookup(f"k{i}") for i in range(1000))


def test_lookup_member_node():
    m = MaglevHash(nodes=_nodes(5), table_size=1019, seed=0)
    members = set(m.nodes)
    assert all(m.lookup(f"k{i}") in members for i in range(1000))


def test_lookup_empty_raises():
    with pytest.raises(MaglevError):
        MaglevHash(table_size=1019, seed=0).lookup("k")


def test_assign_is_lookup_alias():
    m = MaglevHash(nodes=_nodes(5), table_size=1019, seed=0)
    assert all(m.assign(f"k{i}") == m.lookup(f"k{i}") for i in range(500))


def test_single_node_owns_all():
    m = MaglevHash(nodes=["solo"], table_size=1019, seed=0)
    assert all(m.lookup(f"k{i}") == "solo" for i in range(500))


def test_len_and_contains():
    m = MaglevHash(nodes=["a", "b"], table_size=1019, seed=0)
    assert len(m) == 2 and "a" in m and "z" not in m


def test_constructor_dedups_nodes():
    m = MaglevHash(nodes=["a", "a", "b"], table_size=1019, seed=0)
    assert len(m) == 2


# ── even load (the headline property) ─────────────────────────────────────────────

def test_even_load():
    m = MaglevHash(nodes=_nodes(10), table_size=1019, seed=0)
    s = m.stats()
    assert s["load_ratio"] < 1.10            # near-perfect even spread


def test_load_distribution_sums_to_table_size():
    m = MaglevHash(nodes=_nodes(7), table_size=1019, seed=0)
    assert sum(m.load_distribution().values()) == m.table_size


def test_load_distribution_all_nodes_present():
    m = MaglevHash(nodes=_nodes(7), table_size=1019, seed=0)
    dist = m.load_distribution()
    assert set(dist) == set(m.nodes) and all(v > 0 for v in dist.values())


# ── disruption on membership change ───────────────────────────────────────────────

def test_remove_disruption_small():
    m = MaglevHash(nodes=_nodes(10), table_size=1019, seed=0)
    keys = [f"k{i}" for i in range(5000)]
    before = {k: m.lookup(k) for k in keys}
    m.remove_node("n3")
    after = {k: m.lookup(k) for k in keys}
    changed = sum(1 for k in keys if before[k] != after[k])
    assert changed / 5000 < 0.20             # ~1/N + minor churn


def test_no_key_maps_to_removed_node():
    m = MaglevHash(nodes=_nodes(10), table_size=1019, seed=0)
    m.remove_node("n3")
    assert all(m.lookup(f"k{i}") != "n3" for i in range(3000))


# ── determinism ──────────────────────────────────────────────────────────────────

def test_order_independent():
    x = MaglevHash(nodes=["a", "b", "c", "d"], table_size=1019, seed=7)
    y = MaglevHash(nodes=["d", "c", "b", "a"], table_size=1019, seed=7)
    assert all(x.lookup(f"k{i}") == y.lookup(f"k{i}") for i in range(3000))


def test_different_seed_diverges():
    x = MaglevHash(nodes=_nodes(4), table_size=1019, seed=7)
    z = MaglevHash(nodes=_nodes(4), table_size=1019, seed=8)
    assert any(x.lookup(f"k{i}") != z.lookup(f"k{i}") for i in range(3000))


# ── node management ────────────────────────────────────────────────────────────────

def test_add_node_rebuilds():
    m = MaglevHash(nodes=_nodes(4), table_size=1019, seed=0)
    assert m.add_node("e") is True and "e" in m and len(m) == 5
    assert m.stats()["load_ratio"] < 1.15


def test_add_existing_node_false():
    m = MaglevHash(nodes=["a"], table_size=1019, seed=0)
    assert m.add_node("a") is False and len(m) == 1


def test_remove_node_present():
    m = MaglevHash(nodes=["a", "b"], table_size=1019, seed=0)
    assert m.remove_node("a") is True and "a" not in m


def test_remove_node_absent():
    assert MaglevHash(nodes=["a"], table_size=1019, seed=0).remove_node("zzz") is False


def test_numeric_node_ids():
    m = MaglevHash(nodes=[1, 2, 3], table_size=1019, seed=0)
    assert m.lookup("k") in {1, 2, 3}


# ── validation ────────────────────────────────────────────────────────────────────

def test_more_nodes_than_slots_raises():
    with pytest.raises(MaglevError):
        MaglevHash(nodes=["a", "b", "c"], table_size=2, seed=0)   # M=2 prime, 3 nodes


def test_invalid_table_size_raises():
    with pytest.raises(MaglevError):
        MaglevHash(table_size=1)


def test_invalid_seed_raises():
    with pytest.raises(MaglevError):
        MaglevHash(seed="nope")


def test_bool_table_size_rejected():
    with pytest.raises(MaglevError):
        MaglevHash(table_size=True)


def test_nodes_non_iterable_raises():
    with pytest.raises(MaglevError):
        MaglevHash(nodes=123, table_size=1019)


def test_error_stores_detail():
    err = MaglevError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    m = MaglevHash(nodes=["a"], table_size=2003, seed=5)
    assert m.table_size == 2003 and m.seed == 5


def test_nodes_property():
    m = MaglevHash(nodes=["b", "a"], table_size=1019, seed=0)
    assert set(m.nodes) == {"a", "b"}


def test_stats_keys():
    assert set(MaglevHash(table_size=1019, seed=0).stats()) == {
        "num_nodes", "table_size", "nodes", "min_load", "max_load", "load_ratio", "seed"}


def test_stats_values():
    m = MaglevHash(nodes=_nodes(5), table_size=1019, seed=3)
    s = m.stats()
    assert s["num_nodes"] == 5 and s["table_size"] == 1019 and s["seed"] == 3
    assert s["min_load"] > 0 and s["max_load"] >= s["min_load"]


def test_stats_empty():
    s = MaglevHash(table_size=1019, seed=0).stats()
    assert s["num_nodes"] == 0 and s["min_load"] == 0 and s["max_load"] == 0


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    m = MaglevHash(nodes=_nodes(5), table_size=1019, seed=0)
    m.reset()
    assert len(m) == 0


def test_reset_reconfigures():
    m = MaglevHash(nodes=["a"], table_size=1019, seed=0)
    m.reset(table_size=2000, seed=9)
    assert m.table_size == 2003 and m.seed == 9 and len(m) == 0


def test_reset_invalid_raises():
    m = MaglevHash(table_size=1019, seed=0)
    with pytest.raises(MaglevError):
        m.reset(table_size=0)


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_lookups_and_mutations():
    m = MaglevHash(nodes=_nodes(8), table_size=1019, seed=0)
    errors = []

    def reader():
        try:
            for i in range(500):
                m.lookup(f"k{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    def writer(base):
        try:
            for i in range(10):
                m.add_node(f"x-{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = ([threading.Thread(target=reader) for _ in range(6)]
               + [threading.Thread(target=writer, args=(b,)) for b in range(4)])
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert m.lookup("final") in set(m.nodes)
