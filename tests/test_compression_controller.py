"""Tests for the Compression Controller (multi-strategy stream summarisation)."""

from __future__ import annotations

import threading

import pytest

from pradyos.core.compression_controller import (
    CompressionController,
    CompressionControllerError,
)


def _cc(**kw) -> CompressionController:
    return CompressionController(seed=0, **kw)


# ── construction / validation ───────────────────────────────────────────

def test_default_construction():
    cc = _cc()
    s = cc.stats()
    assert "topk" in s["strategies"]
    assert s["active_strategies"]["topk"] is False
    assert s["seed"] == 0


def test_custom_construction():
    cc = CompressionController(topk_k=50, bloom_capacity=1000, minhash_hashes=64, seed=42)
    s = cc.stats()
    assert s["topk_k"] == 50
    assert s["bloom_capacity"] == 1000
    assert s["minhash_hashes"] == 64
    assert s["seed"] == 42


@pytest.mark.parametrize("bad", [0, -1, 1.5, "x"])
def test_invalid_topk_k(bad):
    with pytest.raises(CompressionControllerError):
        CompressionController(topk_k=bad)


@pytest.mark.parametrize("bad", [0, -1, -100, 1.5, "x"])
def test_invalid_bloom_capacity(bad):
    with pytest.raises(CompressionControllerError):
        CompressionController(bloom_capacity=bad)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 2])
def test_invalid_bloom_error_rate(bad):
    with pytest.raises(CompressionControllerError):
        CompressionController(bloom_error_rate=bad)


@pytest.mark.parametrize("bad", [0, -1, -100, 1.5, "x"])
def test_invalid_minhash_hashes(bad):
    with pytest.raises(CompressionControllerError):
        CompressionController(minhash_hashes=bad)


# ── strategies ─────────────────────────────────────────────────────────

def test_strategies_list():
    cc = _cc()
    strs = cc.strategies()
    assert "topk" in strs
    assert "bloom" in strs
    assert "minhash" in strs


# ── feed / summarize topk ──────────────────────────────────────────────

def test_feed_topk():
    cc = _cc(topk_k=3)
    items = ["a", "b", "a", "c", "a", "b", "d"]
    result = cc.feed(items, "topk")
    assert result["strategy"] == "topk"
    assert len(result["items"]) <= 3
    assert result["total"] == 7


def test_feed_topk_empty():
    cc = _cc()
    result = cc.feed([], "topk")
    assert result["strategy"] == "topk"
    assert result["total"] == 0


def test_summarize_topk_before_feed():
    cc = _cc()
    s = cc.summarize("topk")
    assert s["items"] == []


# ── feed / summarize bloom ─────────────────────────────────────────────

def test_feed_bloom():
    cc = _cc(bloom_capacity=1000)
    items = ["x", "y", "z", "x"]
    result = cc.feed(items, "bloom")
    assert result["strategy"] == "bloom"
    assert result["total_fed"] == 4
    assert result["unique_estimate"] == 3


def test_feed_bloom_then_check():
    cc = _cc(bloom_capacity=1000)
    cc.feed(["hello", "world"], "bloom")
    bf = cc._state.bloom
    assert bf is not None
    assert bf.contains("hello") is True
    assert bf.contains("missing") is False


def test_summarize_bloom_before_feed():
    cc = _cc()
    s = cc.summarize("bloom")
    assert s["total_fed"] == 0


# ── feed / summarize minhash ───────────────────────────────────────────

def test_feed_minhash():
    cc = _cc(minhash_hashes=64)
    items = ["king", "man", "queen", "woman"]
    result = cc.feed(items, "minhash")
    assert result["strategy"] == "minhash"
    assert result["signature"] is not None
    assert len(result["signature"]) == 64


def test_summarize_minhash_before_feed():
    cc = _cc()
    s = cc.summarize("minhash")
    assert s["signature"] is None


# ── invalid strategy ───────────────────────────────────────────────────

def test_feed_unknown_strategy():
    cc = _cc()
    with pytest.raises(CompressionControllerError):
        cc.feed(["a"], "nonexistent")


def test_feed_invalid_items():
    cc = _cc()
    with pytest.raises(CompressionControllerError):
        cc.feed("not_a_list", "topk")


def test_summarize_unknown_strategy():
    cc = _cc()
    with pytest.raises(CompressionControllerError):
        cc.summarize("bad")


# ── estimate_size ──────────────────────────────────────────────────────

def test_estimate_topk():
    cc = _cc()
    items = ["a", "b", "a", "c", "d"]
    est = cc.estimate_size(items, "topk")
    assert est["strategy"] == "topk"
    assert est["raw_items"] == 5
    assert est["compression_ratio"] > 0.0


def test_estimate_bloom():
    cc = _cc()
    items = ["a", "b", "c"]
    est = cc.estimate_size(items, "bloom")
    assert est["strategy"] == "bloom"


def test_estimate_minhash():
    cc = _cc()
    items = ["a", "b", "c"]
    est = cc.estimate_size(items, "minhash")
    assert est["strategy"] == "minhash"
    assert est["estimated_compressed_bytes"] == cc._mh_hashes * 8


# ── reset ──────────────────────────────────────────────────────────────

def test_reset_all():
    cc = _cc()
    cc.feed(["a", "b", "c"], "topk")
    cc.feed(["x", "y"], "bloom")
    assert cc._state.topk is not None
    assert cc._state.bloom is not None
    cc.reset()
    assert cc._state.topk is None
    assert cc._state.bloom is None


def test_reset_single_strategy():
    cc = _cc()
    cc.feed(["a"], "topk")
    cc.feed(["x"], "bloom")
    assert cc._state.topk is not None
    assert cc._state.bloom is not None
    cc.reset(strategy="topk")
    assert cc._state.topk is None
    assert cc._state.bloom is not None


# ── determinism ────────────────────────────────────────────────────────

def test_same_seed_deterministic():
    cc1 = CompressionController(minhash_hashes=64, seed=7)
    cc2 = CompressionController(minhash_hashes=64, seed=7)
    items = ["a", "b", "c", "d"]
    r1 = cc1.feed(items, "minhash")
    r2 = cc2.feed(items, "minhash")
    assert r1["signature"] == r2["signature"]


# ── thread safety ──────────────────────────────────────────────────────

def test_concurrent_feed():
    cc = _cc(topk_k=500)
    n_threads = 10
    items_per = 100

    def _work(tid: int):
        items = [f"t{tid}_{i}" for i in range(items_per)]
        cc.feed(items, "topk")

    threads = [threading.Thread(target=_work, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    s = cc.summarize("topk")
    assert s["total"] == n_threads * items_per


def test_concurrent_read_no_crash():
    cc = _cc()
    cc.feed(["a", "b", "c"], "bloom")

    def _check():
        for _ in range(100):
            cc.summarize("bloom")
            cc.strategies()
            cc.stats()

    threads = [threading.Thread(target=_check) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    s = cc.summarize("bloom")
    assert s["total_fed"] == 3
