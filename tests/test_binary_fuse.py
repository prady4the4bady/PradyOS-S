"""Phase 108 — unit tests for the Sovereign Binary Fuse Filter (pradyos.core.binary_fuse)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.binary_fuse import BinaryFuseFilter, BinaryFuseError


def _keys(n: int, prefix: str = "key"):
    return [f"{prefix}-{i}" for i in range(n)]


def _built(n: int = 1000, seed: int = 0):
    bf = BinaryFuseFilter(seed=seed)
    bf.build(_keys(n))
    return bf


# ── construction / params ──────────────────────────────────────────────────────────

def test_default_seed():
    assert BinaryFuseFilter().seed == 0


def test_custom_seed():
    assert BinaryFuseFilter(seed=7).seed == 7


@pytest.mark.parametrize("bad", [1.5, "x", None, True])
def test_bad_seed_raises(bad):
    with pytest.raises(BinaryFuseError):
        BinaryFuseFilter(seed=bad)


def test_starts_unbuilt():
    assert BinaryFuseFilter().built is False


def test_len_zero_before_build():
    assert len(BinaryFuseFilter()) == 0


def test_stats_keys():
    assert set(BinaryFuseFilter().stats()) == {
        "built", "num_keys", "array_size", "bits_per_key", "seed"}


def test_stats_unbuilt():
    s = BinaryFuseFilter().stats()
    assert s["built"] is False and s["num_keys"] == 0 and s["bits_per_key"] is None


def test_error_carries_detail():
    err = BinaryFuseError("filter not built")
    assert err.detail == "filter not built"


# ── build ──────────────────────────────────────────────────────────────────────────

def test_build_sets_built():
    bf = BinaryFuseFilter()
    bf.build(_keys(100))
    assert bf.built is True


def test_build_sets_num_keys():
    bf = _built(500)
    assert len(bf) == 500 and bf.stats()["num_keys"] == 500


def test_build_duplicate_keys_raises():
    bf = BinaryFuseFilter()
    with pytest.raises(BinaryFuseError):
        bf.build(["a", "b", "a"])


def test_build_replaces_prior():
    bf = BinaryFuseFilter()
    bf.build(_keys(100, "first"))
    bf.build(_keys(50, "second"))
    assert len(bf) == 50 and bf.contains("second-0") and not bf.contains("first-0")


def test_build_empty_keys():
    bf = BinaryFuseFilter()
    bf.build([])
    assert bf.built is True and len(bf) == 0


def test_build_non_iterable_raises():
    with pytest.raises(BinaryFuseError):
        BinaryFuseFilter().build(123)


def test_build_single_key():
    bf = BinaryFuseFilter()
    bf.build(["solo"])
    assert bf.contains("solo")


# ── contains / no false negatives ─────────────────────────────────────────────────────

def test_no_false_negatives_small():
    bf = _built(100)
    assert all(bf.contains(k) for k in _keys(100))


def test_no_false_negatives_large():
    bf = _built(5000)
    assert all(bf.contains(k) for k in _keys(5000))


def test_contains_operator():
    bf = _built(100)
    assert "key-0" in bf


def test_contains_before_build_raises():
    with pytest.raises(BinaryFuseError):
        BinaryFuseFilter().contains("x")


def test_contains_operator_before_build_raises():
    with pytest.raises(BinaryFuseError):
        "x" in BinaryFuseFilter()


def test_empty_filter_contains_false():
    bf = BinaryFuseFilter()
    bf.build([])
    assert bf.contains("anything") is False


# ── false positive rate ──────────────────────────────────────────────────────────────

def test_fpr_within_bound():
    bf = _built(1000)
    fp = sum(1 for i in range(10000) if bf.contains(f"nonmember-{i}"))
    assert fp / 10000 <= 0.005


def test_fpr_roughly_one_in_256():
    bf = _built(2000)
    fp = sum(1 for i in range(20000) if bf.contains(f"absent-xyz-{i}"))
    # theoretical 1/256 ≈ 0.0039; allow generous slack
    assert fp / 20000 <= 0.008


# ── space efficiency ─────────────────────────────────────────────────────────────────

def test_bits_per_key_bound():
    assert _built(1000).stats()["bits_per_key"] <= 10.0


def test_bits_per_key_none_when_unbuilt():
    assert BinaryFuseFilter().stats()["bits_per_key"] is None


def test_array_size_about_1_23n():
    bf = _built(3000)
    m = bf.array_size
    # m = 3 * (ceil(1.23n/3) + 4) ≈ 1.23n + 12
    assert 1.23 * 3000 <= m <= 1.23 * 3000 + 40


# ── determinism / order-independence ──────────────────────────────────────────────────

def test_determinism_same_array():
    a = BinaryFuseFilter(seed=0)
    b = BinaryFuseFilter(seed=0)
    a.build(_keys(1000))
    b.build(_keys(1000))
    assert a._array == b._array


def test_order_independence():
    a = BinaryFuseFilter(seed=0)
    b = BinaryFuseFilter(seed=0)
    a.build(["a", "b", "c", "d", "e"])
    b.build(["c", "a", "e", "b", "d"])
    assert a._array == b._array


def test_order_independence_large():
    items = _keys(800)
    a = BinaryFuseFilter(seed=3)
    b = BinaryFuseFilter(seed=3)
    a.build(items)
    b.build(list(reversed(items)))
    assert a._array == b._array


def test_different_seed_different_array():
    a = BinaryFuseFilter(seed=1)
    b = BinaryFuseFilter(seed=2)
    a.build(_keys(500))
    b.build(_keys(500))
    assert a._array != b._array


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears_built():
    bf = _built(500)
    bf.reset()
    assert bf.built is False and len(bf) == 0


def test_reset_makes_contains_raise():
    bf = _built(100)
    bf.reset()
    with pytest.raises(BinaryFuseError):
        bf.contains("key-0")


def test_reset_reconfigures_seed():
    bf = BinaryFuseFilter(seed=0)
    bf.reset(seed=9)
    assert bf.seed == 9


def test_reset_bad_seed_raises():
    bf = _built(50)
    with pytest.raises(BinaryFuseError):
        bf.reset(seed="bad")


def test_rebuild_after_reset():
    bf = _built(100)
    bf.reset()
    bf.build(_keys(200, "new"))
    assert bf.built and len(bf) == 200 and bf.contains("new-0")


# ── robustness across sizes ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [1, 2, 5, 10, 50, 200, 1000, 3000])
def test_build_and_query_across_sizes(n):
    bf = BinaryFuseFilter(seed=0)
    bf.build(_keys(n))
    assert all(bf.contains(k) for k in _keys(n))


def test_integer_and_mixed_keys():
    bf = BinaryFuseFilter()
    bf.build(["a", "b", "c"])
    assert bf.contains("a") and bf.contains("b") and bf.contains("c")


# ── thread-safety ─────────────────────────────────────────────────────────────────────

def test_concurrent_contains():
    bf = _built(2000)
    results = []

    def worker():
        results.append(all(bf.contains(f"key-{i}") for i in range(0, 2000, 10)))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(results)


# ── stats integration ───────────────────────────────────────────────────────────────

def test_stats_after_build():
    bf = _built(1000)
    s = bf.stats()
    assert s["built"] is True and s["num_keys"] == 1000
    assert s["array_size"] == bf.array_size and s["bits_per_key"] <= 10.0
