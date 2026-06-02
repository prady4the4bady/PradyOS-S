"""Phase 119 — unit tests for RendezvousHash (pradyos/core/rendezvous_hash.py)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.rendezvous_hash import RendezvousHash, RendezvousError


def _nodes(n):
    return [f"n{i}" for i in range(n)]


# ── basic correctness ──────────────────────────────────────────────────────────

def test_assign_deterministic():
    r = RendezvousHash(nodes=_nodes(8), seed=0)
    assert all(r.assign(f"k{i}") == r.assign(f"k{i}") for i in range(1000))


def test_assign_returns_a_member_node():
    r = RendezvousHash(nodes=_nodes(5), seed=0)
    members = set(r.nodes)
    assert all(r.assign(f"k{i}") in members for i in range(500))


def test_assign_empty_raises():
    with pytest.raises(RendezvousError):
        RendezvousHash(seed=0).assign("k")


def test_len_and_contains():
    r = RendezvousHash(nodes=["a", "b"], seed=0)
    assert len(r) == 2 and "a" in r and "z" not in r


def test_single_node_gets_everything():
    r = RendezvousHash(nodes=["only"], seed=0)
    assert all(r.assign(f"k{i}") == "only" for i in range(200))


# ── uniform load ─────────────────────────────────────────────────────────────────

def test_uniform_load():
    r = RendezvousHash(nodes=_nodes(8), seed=0)
    counts = {}
    keys = [f"key-{i}" for i in range(8000)]
    for k in keys:
        counts[r.assign(k)] = counts.get(r.assign(k), 0) + 1
    expected = 8000 / 8
    assert len(counts) == 8
    assert max(abs(c - expected) / expected for c in counts.values()) < 0.15


# ── minimal disruption ───────────────────────────────────────────────────────────

def test_remove_only_moves_removed_nodes_keys():
    r = RendezvousHash(nodes=_nodes(8), seed=0)
    keys = [f"k{i}" for i in range(5000)]
    before = {k: r.assign(k) for k in keys}
    r.remove_node("n3")
    after = {k: r.assign(k) for k in keys}
    moved = {k for k in keys if before[k] != after[k]}
    on_n3 = {k for k in keys if before[k] == "n3"}
    assert moved == on_n3
    assert all(after[k] == before[k] for k in keys if before[k] != "n3")


def test_add_only_pulls_keys_to_new_node():
    r = RendezvousHash(nodes=_nodes(8), seed=0)
    keys = [f"k{i}" for i in range(5000)]
    before = {k: r.assign(k) for k in keys}
    r.add_node("NEW")
    after = {k: r.assign(k) for k in keys}
    moved = [k for k in keys if before[k] != after[k]]
    assert all(after[k] == "NEW" for k in moved)
    assert all(after[k] == before[k] for k in keys if after[k] != "NEW")


def test_add_moves_roughly_one_over_n_plus_one():
    r = RendezvousHash(nodes=_nodes(8), seed=0)
    keys = [f"k{i}" for i in range(5000)]
    before = {k: r.assign(k) for k in keys}
    r.add_node("NEW")
    moved = sum(1 for k in keys if before[k] != r.assign(k))
    assert 0.06 < moved / 5000 < 0.16        # ~1/9 ≈ 0.111


# ── weighted ──────────────────────────────────────────────────────────────────────

def test_weighted_load_proportional():
    r = RendezvousHash(seed=0)
    r.add_node("light", weight=1.0)
    r.add_node("heavy", weight=3.0)
    counts = {"light": 0, "heavy": 0}
    for i in range(8000):
        counts[r.assign(f"k{i}")] += 1
    assert 2.4 < counts["heavy"] / counts["light"] < 3.6


def test_reweight_node():
    r = RendezvousHash(nodes=["a", "b"], seed=0)
    r.add_node("a", weight=5.0)              # re-weight existing
    assert r.weight_of("a") == 5.0 and len(r) == 2


def test_weight_of_absent_raises():
    with pytest.raises(RendezvousError):
        RendezvousHash(nodes=["a"], seed=0).weight_of("zzz")


# ── replicas ─────────────────────────────────────────────────────────────────────

def test_replicas_distinct_and_sized():
    r = RendezvousHash(nodes=_nodes(8), seed=0)
    reps = r.get_replicas("key", 3)
    assert len(reps) == 3 and len(set(reps)) == 3


def test_first_replica_is_assign():
    r = RendezvousHash(nodes=_nodes(8), seed=0)
    assert r.get_replicas("key", 3)[0] == r.assign("key")


def test_replicas_capped_at_node_count():
    r = RendezvousHash(nodes=_nodes(4), seed=0)
    assert len(r.get_replicas("k", 99)) == 4


def test_replicas_invalid_k_raises():
    r = RendezvousHash(nodes=_nodes(4), seed=0)
    with pytest.raises(RendezvousError):
        r.get_replicas("k", 0)


def test_replicas_empty_raises():
    with pytest.raises(RendezvousError):
        RendezvousHash(seed=0).get_replicas("k", 1)


# ── determinism ──────────────────────────────────────────────────────────────────

def test_insertion_order_independent():
    x = RendezvousHash(nodes=["a", "b", "c"], seed=7)
    y = RendezvousHash(nodes=["c", "b", "a"], seed=7)
    assert all(x.assign(f"k{i}") == y.assign(f"k{i}") for i in range(2000))


def test_different_seed_diverges():
    x = RendezvousHash(nodes=["a", "b", "c"], seed=7)
    z = RendezvousHash(nodes=["a", "b", "c"], seed=8)
    assert any(x.assign(f"k{i}") != z.assign(f"k{i}") for i in range(2000))


# ── node management ────────────────────────────────────────────────────────────────

def test_add_node():
    r = RendezvousHash(seed=0)
    r.add_node("a")
    assert "a" in r and len(r) == 1


def test_remove_node_present():
    r = RendezvousHash(nodes=["a", "b"], seed=0)
    assert r.remove_node("a") is True and "a" not in r and len(r) == 1


def test_remove_node_absent():
    assert RendezvousHash(nodes=["a"], seed=0).remove_node("zzz") is False


def test_numeric_node_ids():
    r = RendezvousHash(nodes=[1, 2, 3], seed=0)
    assert r.assign("k") in {1, 2, 3}


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_seed_raises():
    with pytest.raises(RendezvousError):
        RendezvousHash(seed="nope")


def test_bool_seed_rejected():
    with pytest.raises(RendezvousError):
        RendezvousHash(seed=True)


def test_invalid_weight_zero_raises():
    with pytest.raises(RendezvousError):
        RendezvousHash(seed=0).add_node("a", weight=0)


def test_invalid_weight_negative_raises():
    with pytest.raises(RendezvousError):
        RendezvousHash(seed=0).add_node("a", weight=-1.0)


def test_nodes_non_iterable_raises():
    with pytest.raises(RendezvousError):
        RendezvousHash(nodes=123, seed=0)


def test_error_stores_detail():
    err = RendezvousError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_seed_property():
    assert RendezvousHash(seed=42).seed == 42


def test_nodes_property_sorted():
    r = RendezvousHash(nodes=["c", "a", "b"], seed=0)
    assert r.nodes == ["a", "b", "c"]


def test_stats_keys():
    assert set(RendezvousHash(seed=0).stats()) == {"num_nodes", "nodes", "total_weight", "seed"}


def test_stats_values():
    r = RendezvousHash(seed=3)
    r.add_node("a", weight=1.0)
    r.add_node("b", weight=2.0)
    s = r.stats()
    assert s["num_nodes"] == 2 and s["total_weight"] == 3.0 and s["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    r = RendezvousHash(nodes=_nodes(5), seed=0)
    r.reset()
    assert len(r) == 0


def test_reset_reconfigures_seed():
    r = RendezvousHash(nodes=["a"], seed=0)
    r.reset(seed=9)
    assert r.seed == 9 and len(r) == 0


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_assigns_and_mutations():
    r = RendezvousHash(nodes=_nodes(8), seed=0)
    errors = []

    def reader():
        try:
            for i in range(500):
                r.assign(f"k{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    def writer(base):
        try:
            for i in range(20):
                r.add_node(f"extra-{base}-{i}")
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = ([threading.Thread(target=reader) for _ in range(6)]
               + [threading.Thread(target=writer, args=(b,)) for b in range(4)])
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert r.assign("final-key") in set(r.nodes)
