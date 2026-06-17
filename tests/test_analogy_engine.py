"""Tests for the Analogy Engine (MinHash-based relational analogy)."""

from __future__ import annotations

import threading

import pytest

from pradyos.core.analogy_engine import AnalogyEngine, AnalogyEngineError


def _ae(**kw) -> AnalogyEngine:
    return AnalogyEngine(seed=0, **kw)


# ── construction / validation ───────────────────────────────────────────

def test_default_construction():
    ae = _ae()
    s = ae.stats()
    assert s["size"] == 0
    assert s["seed"] == 0


def test_custom_construction():
    ae = AnalogyEngine(num_hashes=64, capacity=500, seed=42)
    s = ae.stats()
    assert s["num_hashes"] == 64
    assert s["capacity"] == 500
    assert s["seed"] == 42


@pytest.mark.parametrize("bad", [0, -1, 1.5, "x"])
def test_invalid_num_hashes(bad):
    with pytest.raises(AnalogyEngineError):
        AnalogyEngine(num_hashes=bad)


@pytest.mark.parametrize("bad", [0, -1, -100, 0.5])
def test_invalid_capacity(bad):
    with pytest.raises(AnalogyEngineError):
        AnalogyEngine(capacity=bad)


# ── basic correctness ──────────────────────────────────────────────────

def test_observe_and_keys():
    ae = _ae()
    ae.observe("test", ["king", "man"], ["queen", "woman"])
    assert ae.keys() == ["test"]


def test_observe_replaces_existing():
    ae = _ae()
    ae.observe("x", ["a"], ["b"])
    ae.observe("x", ["a2"], ["b2"])
    s = ae.stats()
    assert s["size"] == 1


def test_observe_requires_string_id():
    ae = _ae()
    with pytest.raises(AnalogyEngineError):
        ae.observe("", ["a"], ["b"])


def test_observe_requires_list_tokens():
    ae = _ae()
    with pytest.raises(AnalogyEngineError):
        ae.observe("x", "not_a_list", ["b"])
    with pytest.raises(AnalogyEngineError):
        ae.observe("x", ["a"], "not_a_list")


# ── analogize ──────────────────────────────────────────────────────────

def test_analogize_empty_returns_empty():
    ae = _ae()
    assert ae.analogize(["x"], ["y"]) == []


def test_analogize_exact_match():
    ae = _ae()
    ae.observe("a1", ["king", "man"], ["queen", "woman"])
    results = ae.analogize(["king", "man"], ["queen", "woman"])
    assert len(results) == 1
    assert results[0]["score"] == 1.0


def test_analogize_partial_match():
    ae = _ae()
    ae.observe("a1", ["king", "man"], ["queen", "woman"])
    ae.observe("a2", ["king", "ruler"], ["queen", "ruler"])
    results = ae.analogize(["king", "man"], ["queen", "woman"], top_k=5)
    assert len(results) >= 1
    assert results[0]["analogy_id"] == "a1"


def test_analogize_top_k():
    ae = _ae()
    for i in range(10):
        ae.observe(f"a{i}", ["x"], [f"y{i}"])
    results = ae.analogize(["x"], ["y0"], top_k=3)
    assert len(results) == 3


def test_analogize_requires_list():
    ae = _ae()
    with pytest.raises(AnalogyEngineError):
        ae.analogize("bad", ["y"])
    with pytest.raises(AnalogyEngineError):
        ae.analogize(["x"], "bad")
    with pytest.raises(AnalogyEngineError):
        ae.analogize(["x"], ["y"], top_k=0)


# ── complete ───────────────────────────────────────────────────────────

def test_complete_empty_returns_empty():
    ae = _ae()
    assert ae.complete(["x"]) == []


def test_complete_simple():
    ae = _ae()
    ae.observe("a1", ["king", "man"], ["queen", "woman"])
    results = ae.complete(["king", "man"])
    assert len(results) >= 1
    assert "queen" in " ".join(results[0]["target_tokens"])


def test_complete_aggregates():
    ae = _ae()
    ae.observe("a1", ["king", "man"], ["queen", "woman"])
    ae.observe("a2", ["king", "man"], ["royal", "female"])
    results = ae.complete(["king", "man"])
    assert len(results) == 2


def test_complete_requires_list():
    ae = _ae()
    with pytest.raises(AnalogyEngineError):
        ae.complete("bad")
    with pytest.raises(AnalogyEngineError):
        ae.complete(["x"], top_k=0)


# ── determinism ────────────────────────────────────────────────────────

def test_same_seed_deterministic():
    ae1 = AnalogyEngine(seed=7)
    ae2 = AnalogyEngine(seed=7)
    for i in range(10):
        ae1.observe(f"a{i}", [f"src{i}"], [f"tgt{i}"])
        ae2.observe(f"a{i}", [f"src{i}"], [f"tgt{i}"])
    r1 = ae1.analogize(["src0"], ["tgt0"])
    r2 = ae2.analogize(["src0"], ["tgt0"])
    assert r1 == r2


# ── capacity / eviction ───────────────────────────────────────────────

def test_eviction():
    ae = AnalogyEngine(capacity=5, seed=0)
    for i in range(10):
        ae.observe(f"a{i}", [f"src{i}"], [f"tgt{i}"])
    assert ae.stats()["size"] <= 5


# ── reset ──────────────────────────────────────────────────────────────

def test_reset_clears():
    ae = _ae()
    ae.observe("x", ["a"], ["b"])
    assert ae.stats()["size"] == 1
    ae.reset()
    assert ae.stats()["size"] == 0
    assert ae.keys() == []


# ── thread safety ──────────────────────────────────────────────────────

def test_concurrent_observe():
    ae = _ae()
    n_threads = 10
    items_per = 50

    def _work(tid: int):
        for i in range(items_per):
            ae.observe(f"t{tid}_{i}", [f"src_{i}"], [f"tgt_{i}"])

    threads = [threading.Thread(target=_work, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ae.stats()["size"] == n_threads * items_per


def test_concurrent_read_no_crash():
    ae = _ae()
    for i in range(20):
        ae.observe(f"a{i}", [f"src{i}"], [f"tgt{i}"])

    def _read():
        for _ in range(50):
            ae.analogize(["src0"], ["tgt0"])
            ae.complete(["src0"])

    threads = [threading.Thread(target=_read) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ae.analogize(["src0"], ["tgt0"])) >= 1
