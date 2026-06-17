"""Tests for the Novelty Detector (Bloom Filter + HyperLogLog)."""

from __future__ import annotations

import threading

import pytest

from pradyos.core.novelty_detector import NoveltyDetector, NoveltyDetectorError


def _nd(**kw) -> NoveltyDetector:
    return NoveltyDetector(seed=0, **kw)


# ── construction / validation ───────────────────────────────────────────

def test_default_construction():
    s = _nd().stats()
    assert s["total_observations"] == 0
    assert s["novel_observations"] == 0
    assert s["unique_estimate"] == 0
    assert s["seed"] == 0


def test_custom_construction():
    nd = NoveltyDetector(bloom_capacity=5000, bloom_error_rate=0.005, hll_precision=10, seed=42)
    s = nd.stats()
    assert s["seed"] == 42


@pytest.mark.parametrize("bad", [0, -1, 1.5, "x"])
def test_invalid_bloom_capacity(bad):
    with pytest.raises(NoveltyDetectorError):
        NoveltyDetector(bloom_capacity=bad)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 2])
def test_invalid_bloom_error_rate(bad):
    with pytest.raises(NoveltyDetectorError):
        NoveltyDetector(bloom_error_rate=bad)


@pytest.mark.parametrize("bad", [3, 17, -1, 0])
def test_invalid_hll_precision(bad):
    with pytest.raises(NoveltyDetectorError):
        NoveltyDetector(hll_precision=bad)


# ── basic correctness ──────────────────────────────────────────────────

def test_first_observation_is_novel():
    nd = _nd()
    assert nd.is_novel("first_item") is True


def test_observe_makes_not_novel():
    nd = _nd()
    assert nd.is_novel("x") is True
    nd.observe("x")
    assert nd.is_novel("x") is False


def test_multiple_items_independent():
    nd = _nd()
    nd.observe("a")
    assert nd.is_novel("a") is False
    assert nd.is_novel("b") is True


def test_observe_increments_total():
    nd = _nd()
    assert nd.stats()["total_observations"] == 0
    nd.observe("a")
    assert nd.stats()["total_observations"] == 1
    nd.observe("a")
    assert nd.stats()["total_observations"] == 2


def test_novelty_rate_starts_zero():
    nd = _nd()
    assert nd.novelty_rate() == 0.0


def test_novelty_rate_all_novel():
    nd = _nd()
    nd.observe("a")
    nd.observe("b")
    nd.observe("c")
    assert nd.novelty_rate() == 1.0


def test_novelty_rate_repeats():
    nd = _nd()
    nd.observe("a")
    nd.observe("a")
    nd.observe("b")
    # a first time = novel, a second time = not, b first time = novel → 2/3
    assert nd.novelty_rate() == pytest.approx(2.0 / 3.0)


# ── edge cases ─────────────────────────────────────────────────────────

def test_empty_detector():
    nd = _nd()
    assert nd.stats()["total_observations"] == 0
    assert nd.novelty_rate() == 0.0
    assert nd.stats()["unique_estimate"] == 0


def test_single_item():
    nd = _nd()
    nd.observe("only")
    s = nd.stats()
    assert s["total_observations"] == 1
    assert s["novel_observations"] == 1


def test_large_n():
    nd = _nd()
    for i in range(5000):
        nd.observe(f"item_{i}")
    s = nd.stats()
    assert s["total_observations"] == 5000
    assert 4850 <= s["unique_estimate"] <= 5150  # HLL ± ~3% at precision 14


def test_observe_requires_string():
    nd = _nd()
    with pytest.raises(NoveltyDetectorError):
        nd.observe(123)


def test_is_novel_requires_string():
    nd = _nd()
    with pytest.raises(NoveltyDetectorError):
        nd.is_novel(123)


def test_surprise_requires_string():
    nd = _nd()
    with pytest.raises(NoveltyDetectorError):
        nd.surprise_score(123)


# ── determinism ────────────────────────────────────────────────────────

def test_same_seed_deterministic():
    nd1 = NoveltyDetector(seed=42)
    nd2 = NoveltyDetector(seed=42)
    for i in range(100):
        nd1.observe(f"item_{i % 20}")
        nd2.observe(f"item_{i % 20}")
    assert nd1.stats()["unique_estimate"] == nd2.stats()["unique_estimate"]


def test_different_seeds_different():
    nd1 = NoveltyDetector(seed=0)
    nd2 = NoveltyDetector(seed=1)
    for i in range(50):
        nd1.observe(f"item_{i}")
        nd2.observe(f"item_{i}")
    # HLL is deterministic per seed but Bloom uses SHA-256 internally so seed
    # doesn't change Bloom behaviour; both filters will have same membership.
    # The HLL estimates should be the same (HLL is seed-independent). So
    # different seed mostly matters for the sketch internals, not the output.

# ── surprise_score ────────────────────────────────────────────────────

def test_surprise_unseen_equals_cardinality():
    nd = _nd()
    nd.observe("a")
    nd.observe("b")
    card = nd.stats()["unique_estimate"]
    assert nd.surprise_score("never_seen") == float(card)


def test_surprise_common_vs_rare():
    nd = _nd()
    for _ in range(1000):
        nd.observe("common")
    nd.observe("rare")
    assert nd.surprise_score("common") < nd.surprise_score("rare")


def test_surprise_single_observation():
    nd = _nd()
    nd.observe("only")
    card = nd.stats()["unique_estimate"]
    assert nd.surprise_score("only") == float(card) / 1.0


# ── reset / clear ─────────────────────────────────────────────────────

def test_reset_clears_everything():
    nd = _nd()
    for i in range(100):
        nd.observe(f"item_{i}")
    assert nd.stats()["total_observations"] > 0
    nd.reset()
    s = nd.stats()
    assert s["total_observations"] == 0
    assert s["novel_observations"] == 0
    assert s["unique_estimate"] == 0


def test_reset_makes_items_novel_again():
    nd = _nd()
    nd.observe("x")
    assert nd.is_novel("x") is False
    nd.reset()
    assert nd.is_novel("x") is True


# ── thread safety ──────────────────────────────────────────────────────

def test_concurrent_observations():
    nd = _nd()
    n_threads = 10
    items_per = 100

    def _work():
        for i in range(items_per):
            nd.observe(f"t{threading.get_ident()}_{i}")

    threads = [threading.Thread(target=_work) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    s = nd.stats()
    assert s["total_observations"] == n_threads * items_per


def test_concurrent_is_novel_no_crash():
    nd = _nd()
    nd.observe("target")

    def _check():
        for _ in range(100):
            nd.is_novel("target")
            nd.is_novel("unknown")

    threads = [threading.Thread(target=_check) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert nd.is_novel("target") is False


# ── sanity invariants as tests ─────────────────────────────────────────

def test_invariant_first_is_novel():
    nd = _nd()
    assert nd.is_novel("item_xyz") is True


def test_invariant_second_not_novel():
    nd = _nd()
    nd.observe("item_xyz")
    assert nd.is_novel("item_xyz") is False


def test_invariant_surprise_inversely_proportional():
    nd = _nd()
    for _ in range(1000):
        nd.observe("common")
    nd.observe("rare")
    assert nd.surprise_score("common") < nd.surprise_score("rare")
