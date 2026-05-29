"""Phase 73 — unit tests for HashRing (consistent hashing with virtual nodes)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.hash_ring import DEFAULT_REPLICAS, HashRing, NodeNotFoundError


KEYS = [f"key-{i}" for i in range(3000)]


# ── construction ──────────────────────────────────────────────────────────────

def test_default_replicas():
    r = HashRing()
    assert r.stats()["replicas"] == DEFAULT_REPLICAS
    assert r.nodes() == []


def test_init_with_nodes():
    r = HashRing(["A", "B"])
    assert r.nodes() == ["A", "B"]


def test_init_invalid_replicas_raises():
    with pytest.raises(ValueError):
        HashRing(replicas=0)
    with pytest.raises(ValueError):
        HashRing(replicas=-1)


# ── membership ────────────────────────────────────────────────────────────────

def test_add_node_registers():
    r = HashRing()
    r.add_node("A")
    assert r.has_node("A")
    assert r.nodes() == ["A"]


def test_add_node_idempotent():
    r = HashRing(replicas=50)
    r.add_node("A")
    points = r.stats()["virtual_points"]
    r.add_node("A")
    assert r.nodes() == ["A"]
    assert r.stats()["virtual_points"] == points


def test_nodes_sorted():
    r = HashRing(["C", "A", "B"])
    assert r.nodes() == ["A", "B", "C"]


def test_remove_node():
    r = HashRing(["A", "B"])
    r.remove_node("A")
    assert not r.has_node("A")
    assert r.nodes() == ["B"]


def test_remove_unknown_raises():
    r = HashRing(["A"])
    with pytest.raises(NodeNotFoundError):
        r.remove_node("ghost")


def test_node_not_found_carries_name():
    r = HashRing()
    try:
        r.remove_node("ghost")
    except NodeNotFoundError as exc:
        assert exc.node == "ghost"
        assert "ghost" in str(exc)
    else:  # pragma: no cover
        pytest.fail("expected NodeNotFoundError")


# ── lookup ────────────────────────────────────────────────────────────────────

def test_get_node_empty_ring_returns_none():
    assert HashRing().get_node("x") is None


def test_get_node_is_deterministic():
    r = HashRing(["A", "B", "C"])
    assert r.get_node("key-1") == r.get_node("key-1")


def test_get_node_returns_a_member():
    r = HashRing(["A", "B", "C"])
    assert r.get_node("anything") in {"A", "B", "C"}


def test_get_nodes_returns_distinct():
    r = HashRing(["A", "B", "C"])
    got = r.get_nodes("x", 2)
    assert len(got) == 2
    assert len(set(got)) == 2


def test_get_nodes_caps_at_node_count():
    r = HashRing(["A", "B", "C"])
    assert sorted(r.get_nodes("x", 10)) == ["A", "B", "C"]


def test_get_nodes_empty_ring():
    assert HashRing().get_nodes("x", 3) == []


def test_get_nodes_nonpositive_count():
    r = HashRing(["A", "B"])
    assert r.get_nodes("x", 0) == []
    assert r.get_nodes("x", -1) == []


# ── balance ───────────────────────────────────────────────────────────────────

def test_distribution_is_reasonably_balanced():
    r = HashRing(["A", "B", "C"])
    dist = r.distribution(KEYS)
    assert set(dist) == {"A", "B", "C"}
    # generous: each node owns >15% of keys (ideal is ~33%)
    assert all(count > len(KEYS) * 0.15 for count in dist.values())


def test_distribution_counts_sum_to_total():
    r = HashRing(["A", "B", "C"])
    assert sum(r.distribution(KEYS).values()) == len(KEYS)


# ── the consistent-hashing guarantee ──────────────────────────────────────────

def test_removing_node_only_moves_its_own_keys():
    r = HashRing(["A", "B", "C"])
    before = {k: r.get_node(k) for k in KEYS}
    r.remove_node("C")
    after = {k: r.get_node(k) for k in KEYS}
    # every key NOT owned by C keeps its node; every moved key was owned by C
    assert all(after[k] == before[k] for k in KEYS if before[k] != "C")
    assert all(before[k] == "C" for k in KEYS if before[k] != after[k])


def test_adding_node_only_pulls_keys_to_it():
    r = HashRing(["A", "B"])
    before = {k: r.get_node(k) for k in KEYS}
    r.add_node("D")
    after = {k: r.get_node(k) for k in KEYS}
    # a key either stays put or moves to the new node D — never A<->B churn
    assert all(after[k] in (before[k], "D") for k in KEYS)
    assert any(after[k] == "D" for k in KEYS)


# ── stats / clear ─────────────────────────────────────────────────────────────

def test_stats_keys():
    r = HashRing(["A"], replicas=10)
    stats = r.stats()
    for key in ("nodes", "node_count", "replicas", "virtual_points"):
        assert key in stats


def test_virtual_points_equal_replicas_times_nodes():
    r = HashRing(["A", "B", "C"], replicas=20)
    assert r.stats()["virtual_points"] == 20 * 3


def test_replicas_count_scales_points():
    assert HashRing(["A"], replicas=200).stats()["virtual_points"] == 200


def test_clear_resets_ring():
    r = HashRing(["A", "B"])
    r.clear()
    assert r.nodes() == []
    assert r.get_node("x") is None
    assert r.stats()["virtual_points"] == 0


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_add_and_lookup_is_thread_safe():
    r = HashRing(replicas=20)
    errors: list[Exception] = []

    def worker(idx: int) -> None:
        try:
            r.add_node(f"node-{idx}")
            for k in range(50):
                r.get_node(f"k-{idx}-{k}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(r.nodes()) == 10
    assert r.get_node("anything") in set(r.nodes())
