"""Phase 105 — unit tests for the Sovereign Q-Digest (pradyos.core.q_digest)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.q_digest import QDigest, QDigestError


def _uniform(seed: int = 42, n: int = 10000, hi: int = 1000):
    rnd = random.Random(seed)
    return [rnd.randrange(0, hi) for _ in range(n)]


def _true_pct(values, p):
    s = sorted(values)
    return s[min(len(s) - 1, int(p * len(s)))]


def _loaded(seed: int = 42, vr: int = 1024, k: int = 100):
    qd = QDigest(compression_factor=k, value_range=vr, seed=0)
    for v in _uniform(seed):
        qd.add(v)
    return qd


# ── construction / params ──────────────────────────────────────────────────────────

def test_default_params():
    qd = QDigest()
    assert qd.compression_factor == 100 and qd.value_range == 65536 and qd.seed == 0


def test_custom_params():
    qd = QDigest(compression_factor=50, value_range=4096, seed=7)
    assert (qd.compression_factor, qd.value_range, qd.seed) == (50, 4096, 7)


def test_len_starts_zero():
    assert len(QDigest()) == 0


def test_stats_keys():
    assert set(QDigest().stats()) == {
        "compression_factor", "value_range", "total_count", "num_nodes",
        "theoretical_max_nodes"}


def test_stats_initial():
    s = QDigest().stats()
    assert s["total_count"] == 0 and s["num_nodes"] == 0


def test_theoretical_max_is_k_log_sigma():
    qd = QDigest(compression_factor=100, value_range=65536)
    # capacity 65536 -> 16 levels
    assert qd.stats()["theoretical_max_nodes"] == 100 * 16


def test_value_range_rounds_up_to_pow2_internally():
    qd = QDigest(compression_factor=10, value_range=1000)
    qd.add(999)
    assert qd.value_range == 1000  # reported range unchanged


# ── validation ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [0, -1, 1.5, "x", None, True])
def test_bad_compression_factor_raises(bad):
    with pytest.raises(QDigestError):
        QDigest(compression_factor=bad)


@pytest.mark.parametrize("bad", [0, 1, -4, 2.0, "x", None])
def test_bad_value_range_raises(bad):
    with pytest.raises(QDigestError):
        QDigest(value_range=bad)


@pytest.mark.parametrize("bad", [1.5, "x", None, True])
def test_bad_seed_raises(bad):
    with pytest.raises(QDigestError):
        QDigest(seed=bad)


def test_error_carries_detail():
    err = QDigestError(-5)
    assert err.detail == -5


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_increments_total():
    qd = QDigest(value_range=64)
    qd.add(10)
    qd.add(10)
    assert len(qd) == 2 and qd.total_count == 2


def test_add_with_count():
    qd = QDigest(value_range=64)
    qd.add(5, count=40)
    assert qd.total_count == 40


def test_add_out_of_range_raises():
    qd = QDigest(value_range=1000)
    with pytest.raises(QDigestError):
        qd.add(1000)
    with pytest.raises(QDigestError):
        qd.add(-1)


def test_add_bad_count_raises():
    qd = QDigest(value_range=64)
    with pytest.raises(QDigestError):
        qd.add(1, count=0)
    with pytest.raises(QDigestError):
        qd.add(1, count=-3)


def test_add_non_int_value_raises():
    qd = QDigest(value_range=64)
    with pytest.raises(QDigestError):
        qd.add(3.5)
    with pytest.raises(QDigestError):
        qd.add(True)


def test_add_boundary_values():
    qd = QDigest(value_range=1000)
    qd.add(0)
    qd.add(999)
    assert qd.total_count == 2


# ── quantile ───────────────────────────────────────────────────────────────────────

def test_quantile_empty_raises():
    with pytest.raises(QDigestError):
        QDigest().quantile(0.5)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5, "x", None, True])
def test_quantile_bad_q_raises(bad):
    qd = QDigest(value_range=64)
    qd.add(1)
    with pytest.raises(QDigestError):
        qd.quantile(bad)


def test_quantile_uniform_p50():
    p50 = _loaded().quantile(0.50)
    assert 475 <= p50 <= 525


def test_quantile_tail_p99_within_5pct():
    p99 = _loaded().quantile(0.99)
    assert 990 * 0.95 <= p99 <= 990 * 1.05


def test_quantile_monotonic_strict():
    qd = _loaded()
    q25, q50, q75, q99 = (qd.quantile(0.25), qd.quantile(0.50),
                          qd.quantile(0.75), qd.quantile(0.99))
    assert q25 <= q50 <= q75 <= q99


def test_quantile_single_value():
    qd = QDigest(value_range=1000)
    qd.add(42, count=100)
    assert qd.quantile(0.5) == 42


def test_quantile_skewed_distribution():
    qd = QDigest(compression_factor=100, value_range=1024)
    for v in ([10] * 9000 + [900] * 1000):
        qd.add(v)
    assert qd.quantile(0.5) <= 50          # mass concentrated low
    assert qd.quantile(0.95) >= 800


# ── rank ───────────────────────────────────────────────────────────────────────────

def test_rank_monotonic_nondecreasing():
    qd = _loaded()
    ranks = [qd.rank(v) for v in range(0, 1000, 100)]
    assert ranks == sorted(ranks)


def test_rank_full_at_top():
    qd = QDigest(value_range=1000)
    for v in (1, 2, 3, 4):
        qd.add(v)
    assert qd.rank(999) == 4


def test_rank_zero_below_all():
    qd = QDigest(value_range=1000)
    qd.add(500, count=10)
    assert qd.rank(0) == 0


def test_rank_bad_value_raises():
    qd = QDigest(value_range=64)
    qd.add(1)
    with pytest.raises(QDigestError):
        qd.rank(2.5)


# ── merge ──────────────────────────────────────────────────────────────────────────

def test_merge_combines_counts():
    a = QDigest(value_range=1000)
    b = QDigest(value_range=1000)
    a.add(100, count=30)
    b.add(200, count=70)
    a.merge(b)
    assert a.total_count == 100


def test_merge_p50_accuracy():
    all_vals = _uniform(seed=7)
    a = QDigest(compression_factor=100, value_range=1024)
    b = QDigest(compression_factor=100, value_range=1024)
    for v in all_vals[:5000]:
        a.add(v)
    for v in all_vals[5000:]:
        b.add(v)
    a.merge(b)
    true_p50 = _true_pct(all_vals, 0.50)
    assert abs(a.quantile(0.50) - true_p50) / true_p50 <= 0.05


def test_merge_returns_self():
    a = QDigest(value_range=64)
    b = QDigest(value_range=64)
    a.add(1)
    assert a.merge(b) is a


def test_merge_mismatched_universe_raises():
    a = QDigest(value_range=1000)
    b = QDigest(value_range=2000)
    with pytest.raises(QDigestError):
        a.merge(b)


def test_merge_non_qdigest_raises():
    with pytest.raises(QDigestError):
        QDigest().merge({"not": "a digest"})


def test_merge_does_not_mutate_other():
    a = QDigest(value_range=1000)
    b = QDigest(value_range=1000)
    for v in range(100):
        b.add(v)
    before = b.total_count
    a.merge(b)
    assert b.total_count == before


# ── compression ────────────────────────────────────────────────────────────────────

def test_compression_bound():
    qd = _loaded()
    assert qd.num_nodes <= 4 * 100 * math.log2(1024)


def test_compression_smaller_k_fewer_nodes():
    big_k = _loaded(k=200).num_nodes
    small_k = _loaded(k=20).num_nodes
    assert small_k <= big_k


def test_low_count_keeps_full_resolution():
    # n < k → threshold floor(n/k) == 0 → no merging, exact leaves
    qd = QDigest(compression_factor=100, value_range=1024)
    for v in (10, 20, 30):
        qd.add(v)
    assert qd.num_nodes == 3


# ── determinism ──────────────────────────────────────────────────────────────────────

def test_determinism_same_tree_and_quantiles():
    data = _uniform(seed=99)
    a = QDigest(compression_factor=100, value_range=1024, seed=0)
    b = QDigest(compression_factor=100, value_range=1024, seed=0)
    for v in data:
        a.add(v)
    for v in data:
        b.add(v)
    assert a._tree == b._tree
    assert all(a.quantile(q) == b.quantile(q) for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.99))


def test_insertion_order_independent_totals():
    data = _uniform(seed=3, n=2000)
    a = QDigest(compression_factor=50, value_range=1024)
    b = QDigest(compression_factor=50, value_range=1024)
    for v in data:
        a.add(v)
    for v in reversed(data):
        b.add(v)
    assert a.total_count == b.total_count == 2000


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears():
    qd = _loaded()
    qd.reset()
    assert qd.total_count == 0 and qd.num_nodes == 0


def test_reset_reconfigures():
    qd = QDigest(compression_factor=100, value_range=1024)
    qd.reset(compression_factor=25, value_range=4096, seed=5)
    assert (qd.compression_factor, qd.value_range, qd.seed) == (25, 4096, 5)


def test_reset_bad_config_raises():
    qd = QDigest()
    with pytest.raises(QDigestError):
        qd.reset(compression_factor=0)


def test_reset_then_usable():
    qd = _loaded()
    qd.reset(value_range=64)
    qd.add(10, count=5)
    assert qd.quantile(0.5) == 10


# ── thread-safety ─────────────────────────────────────────────────────────────────────

def test_concurrent_adds():
    qd = QDigest(compression_factor=50, value_range=1024)

    def worker():
        rnd = random.Random()
        for _ in range(500):
            qd.add(rnd.randrange(0, 1000))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert qd.total_count == 8 * 500


# ── stats integration ───────────────────────────────────────────────────────────────

def test_stats_after_load():
    qd = _loaded()
    s = qd.stats()
    assert s["total_count"] == 10000 and s["num_nodes"] == qd.num_nodes
    assert s["compression_factor"] == 100 and s["value_range"] == 1024
