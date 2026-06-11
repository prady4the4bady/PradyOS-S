"""Phase 102 — unit tests for the Sovereign HeavyKeeper core (pradyos.core.heavykeeper)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.heavykeeper import HeavyKeeper, HeavyKeeperError


def _stream(seed: int = 1, heavy: int = 1000, hot: int = 100, n_hot: int = 9, total: int = 10000):
    rnd = random.Random(seed)
    s = ["HEAVY"] * heavy
    for i in range(n_hot):
        s += [f"hot{i}"] * hot
    produced, nid = 0, 0
    target = total - heavy - hot * n_hot
    while produced < target:
        c = min(rnd.randint(1, 4), target - produced)
        s += [f"noise{nid}"] * c
        produced += c
        nid += 1
    rnd.shuffle(s)
    return s


# ── construction / basics ──────────────────────────────────────────────────────

def test_default_params():
    hk = HeavyKeeper()
    assert hk.k == 10 and hk.width == 1024 and hk.depth == 4 and hk.decay == 1.08 and hk.seed == 0


def test_custom_params():
    hk = HeavyKeeper(k=5, width=256, depth=3, decay=1.5, seed=9)
    assert (hk.k, hk.width, hk.depth, hk.decay, hk.seed) == (5, 256, 3, 1.5, 9)


def test_stats_keys():
    assert set(HeavyKeeper().stats()) == {"k", "width", "depth", "decay", "seed", "tracked", "total"}


def test_stats_initial():
    s = HeavyKeeper().stats()
    assert s["tracked"] == 0 and s["total"] == 0


def test_len_is_tracked_count():
    hk = HeavyKeeper(k=10)
    for x in ("a", "b", "c"):
        hk.add(x)
    assert len(hk) == 3


# ── add / query ─────────────────────────────────────────────────────────────────

def test_add_returns_estimate():
    hk = HeavyKeeper()
    assert hk.add("x") == 1


def test_add_increments():
    hk = HeavyKeeper()
    hk.add("x")
    assert hk.add("x") == 2


def test_add_count_batch():
    hk = HeavyKeeper()
    assert hk.add("x", 50) == 50


def test_query_absent_is_zero():
    assert HeavyKeeper().query("never-seen") == 0


def test_query_after_add():
    hk = HeavyKeeper()
    hk.add("x", 7)
    assert hk.query("x") == 7


def test_total_tracks_occurrences():
    hk = HeavyKeeper()
    hk.add("a", 10)
    hk.add("b", 5)
    assert hk.stats()["total"] == 15


def test_integer_and_mixed_items():
    hk = HeavyKeeper()
    hk.add(42, 3)
    hk.add("42", 1)
    assert hk.query(42) == 3            # 42 and "42" are distinct items


# ── heavy-hitter detection / accuracy / eviction ────────────────────────────────

def test_detects_all_heavy_hitters():
    hk = HeavyKeeper(k=10, seed=0)
    for x in _stream(seed=1):
        hk.add(x)
    items = {it for it, _ in hk.top_k(10)}
    expected = {"HEAVY"} | {f"hot{i}" for i in range(9)}
    assert expected <= items


def test_top_item_frequency_within_20pct():
    hk = HeavyKeeper(k=10, seed=0)
    for x in _stream(seed=1):
        hk.add(x)
    est = dict(hk.top_k(10))["HEAVY"]
    assert 800 <= est <= 1200          # true frequency 1000, ±20%


def test_low_frequency_items_evicted():
    hk = HeavyKeeper(k=10, seed=0)
    for x in _stream(seed=1):
        hk.add(x)
    items = [it for it, _ in hk.top_k(10)]
    assert not any(it.startswith("noise") for it in items)


def test_estimate_is_max_not_min():
    # A clean heavy hitter should be estimated at (near) its true count, not undercounted
    # to a minimum row as Count-Min would.
    hk = HeavyKeeper(seed=0)
    hk.add("solo", 500)
    assert hk.query("solo") == 500


# ── decay sensitivity ───────────────────────────────────────────────────────────

def _bucket_mass(hk: HeavyKeeper) -> int:
    return sum(sum(row) for row in hk._cnt)


def test_lower_decay_forgets_faster():
    stream = _stream(seed=1)
    masses = {}
    for dec in (1.02, 1.5):
        hk = HeavyKeeper(k=10, width=1024, depth=4, decay=dec, seed=0)
        for x in stream:
            hk.add(x)
        masses[dec] = _bucket_mass(hk)
    # aggressive decay (1.02) evicts more → less surviving bucket mass than stable (1.5)
    assert masses[1.02] < masses[1.5]


def test_higher_decay_more_stable_counts():
    stream = _stream(seed=1)
    hot_avg = {}
    for dec in (1.02, 1.5):
        hk = HeavyKeeper(k=10, decay=dec, seed=0)
        for x in stream:
            hk.add(x)
        hot_avg[dec] = sum(hk.query(f"hot{i}") for i in range(9)) / 9
    assert hot_avg[1.5] >= hot_avg[1.02]


# ── determinism ─────────────────────────────────────────────────────────────────

def test_determinism_same_seed_same_stream():
    stream = _stream(seed=2)
    a = HeavyKeeper(seed=7)
    b = HeavyKeeper(seed=7)
    for x in stream:
        a.add(x)
    for x in stream:
        b.add(x)
    assert a.top_k(10) == b.top_k(10)


def test_different_seed_may_differ_but_detects():
    stream = _stream(seed=2)
    a = HeavyKeeper(seed=1)
    b = HeavyKeeper(seed=2)
    for x in stream:
        a.add(x)
        b.add(x)
    # regardless of seed, the dominant hitter is found
    assert a.top_k(1)[0][0] == "HEAVY" and b.top_k(1)[0][0] == "HEAVY"


# ── top_k semantics ─────────────────────────────────────────────────────────────

def test_top_k_sorted_descending():
    hk = HeavyKeeper(k=5)
    hk.add("a", 30)
    hk.add("b", 10)
    hk.add("c", 20)
    counts = [c for _, c in hk.top_k()]
    assert counts == sorted(counts, reverse=True)


def test_top_k_bounded_by_k():
    hk = HeavyKeeper(k=3)
    for i in range(20):
        hk.add(f"item{i}", i + 1)
    assert len(hk.top_k()) == 3


def test_top_k_n_parameter():
    hk = HeavyKeeper(k=10)
    for i in range(10):
        hk.add(f"item{i}", i + 1)
    assert len(hk.top_k(4)) == 4


def test_top_k_default_n_is_k():
    hk = HeavyKeeper(k=6)
    for i in range(10):
        hk.add(f"item{i}", i + 1)
    assert len(hk.top_k()) == 6


def test_top_k_keeps_largest():
    hk = HeavyKeeper(k=2)
    hk.add("small", 1)
    hk.add("big", 100)
    hk.add("mid", 50)
    items = {it for it, _ in hk.top_k()}
    assert items == {"big", "mid"}


# ── concurrency ─────────────────────────────────────────────────────────────────

def test_concurrent_adds_no_corruption():
    hk = HeavyKeeper(k=10, seed=0)
    stream = _stream(seed=3)
    parts = [stream[i::8] for i in range(8)]

    def worker(part):
        for x in part:
            hk.add(x)

    threads = [threading.Thread(target=worker, args=(p,)) for p in parts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(hk._heap) <= 10
    assert len(hk._pos) == len(hk._heap)            # index map consistent (no corruption)
    assert "HEAVY" in {it for it, _ in hk.top_k(10)}


# ── validation ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs", [
    {"k": 0}, {"k": -1}, {"k": True},
    {"width": 0}, {"depth": 0},
    {"decay": 1.0}, {"decay": 0.5}, {"decay": True},
    {"seed": "x"},
])
def test_invalid_config_raises(kwargs):
    with pytest.raises(HeavyKeeperError):
        HeavyKeeper(**kwargs)


def test_add_bad_count_raises():
    hk = HeavyKeeper()
    for bad in (0, -3, True, "5", 1.5):
        with pytest.raises(HeavyKeeperError):
            hk.add("x", bad)


def test_error_detail_attribute():
    try:
        HeavyKeeper(k=0)
    except HeavyKeeperError as exc:
        assert exc.detail == 0
    else:
        pytest.fail("expected HeavyKeeperError")


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears():
    hk = HeavyKeeper()
    hk.add("a", 100)
    hk.reset()
    assert hk.stats()["total"] == 0 and hk.stats()["tracked"] == 0 and hk.query("a") == 0


def test_reset_reconfigures():
    hk = HeavyKeeper(width=1024)
    hk.reset(width=2048, decay=1.2)
    assert hk.width == 2048 and hk.decay == 1.2


def test_reset_bad_config_raises():
    hk = HeavyKeeper()
    with pytest.raises(HeavyKeeperError):
        hk.reset(decay=1.0)


def test_reset_restores_determinism():
    stream = _stream(seed=4)
    hk = HeavyKeeper(seed=5)
    for x in stream:
        hk.add(x)
    first = hk.top_k(10)
    hk.reset()
    for x in stream:
        hk.add(x)
    assert hk.top_k(10) == first
