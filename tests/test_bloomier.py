"""Phase 114 — unit tests for BloomierFilter (pradyos/core/bloomier.py)."""
from __future__ import annotations

import random
import threading

import pytest

from pradyos.core.bloomier import BloomierFilter, BloomierError


class _DupMapping:
    """A dict-like whose .items() yields duplicate keys (to exercise the dup check)."""
    def items(self):
        return [("a", 1), ("a", 2), ("b", 3)]


# ── exact retrieval (the core correctness property) ──────────────────────────────

def test_exact_value_for_every_member_small():
    m = {"apple": 1, "banana": 2, "cherry": 3}
    bf = BloomierFilter(seed=0)
    bf.build(m)
    assert all(bf.get(k) == v for k, v in m.items())


def test_exact_value_for_every_member_large():
    m = {f"key-{i}": i * 7 + 1 for i in range(3000)}
    bf = BloomierFilter(seed=0)
    bf.build(m)
    assert [k for k, v in m.items() if bf.get(k) != v] == []


def test_len_tracks_keys():
    bf = BloomierFilter(seed=0)
    bf.build({f"k{i}": i for i in range(250)})
    assert len(bf) == 250


def test_get_default_for_non_member():
    bf = BloomierFilter(seed=0)
    bf.build({"a": 1})
    assert bf.get("zzz-not-present") is None


def test_get_custom_default():
    bf = BloomierFilter(seed=0)
    bf.build({"a": 1})
    assert bf.get("missing", default="DEFAULT") == "DEFAULT"


def test_single_key_map():
    bf = BloomierFilter(seed=0)
    bf.build({"only": "value"})              # n=1 → value_bits=0 edge case
    assert bf.get("only") == "value" and len(bf) == 1


# ── value types ──────────────────────────────────────────────────────────────────

def test_arbitrary_and_unhashable_values():
    m = {"a": [1, 2, 3], "b": {"x": 1}, "c": "str", "d": 42, "e": None, "f": 3.14}
    bf = BloomierFilter(seed=0)
    bf.build(m)
    assert all(bf.get(k) == v for k, v in m.items())


def test_numeric_keys():
    m = {i: i * i for i in range(100)}
    bf = BloomierFilter(seed=0)
    bf.build(m)
    assert all(bf.get(i) == i * i for i in range(100))


# ── false-positive rate ──────────────────────────────────────────────────────────

def test_non_member_fp_rate_bounded():
    bf = BloomierFilter(fingerprint_bits=8, seed=0)
    bf.build({f"present-{i}": i for i in range(2000)})
    fp = sum(1 for i in range(10000) if bf.get(f"absent-{i}") is not None)
    assert fp / 10000 < 0.02              # theory ~2^-8 = 0.0039


def test_wider_fingerprint_lowers_fp():
    m = {f"present-{i}": i for i in range(2000)}
    bf16 = BloomierFilter(fingerprint_bits=16, seed=0)
    bf16.build(m)
    fp = sum(1 for i in range(10000) if bf16.get(f"absent-{i}") is not None)
    assert fp / 10000 < 0.001


# ── determinism / order independence / immutability ──────────────────────────────

def test_build_deterministic():
    m = {f"k{i}": i for i in range(1000)}
    a = BloomierFilter(seed=3)
    a.build(m)
    b = BloomierFilter(seed=3)
    b.build(m)
    assert a._array == b._array and a._values == b._values


def test_order_independent_build():
    m = {f"k{i}": i for i in range(1000)}
    keys = list(m.keys())
    random.Random(1).shuffle(keys)
    shuffled = {k: m[k] for k in keys}
    a = BloomierFilter(seed=0)
    a.build(m)
    c = BloomierFilter(seed=0)
    c.build(shuffled)
    assert a._array == c._array


def test_rebuild_replaces():
    bf = BloomierFilter(seed=0)
    bf.build({"old": 1})
    bf.build({"new": 2})
    assert bf.get("new") == 2 and bf.get("old") is None and len(bf) == 1


def test_build_across_sizes():
    for n in (1, 2, 3, 5, 10, 64, 300):
        m = {f"k{i}": f"v{i}" for i in range(n)}
        bf = BloomierFilter(seed=0)
        bf.build(m)
        assert all(bf.get(k) == v for k, v in m.items()), f"failed at n={n}"


# ── empty ──────────────────────────────────────────────────────────────────────────

def test_empty_build():
    bf = BloomierFilter(seed=0)
    bf.build({})
    assert bf.built is True and len(bf) == 0 and bf.get("anything") is None


def test_empty_contains_false():
    bf = BloomierFilter(seed=0)
    bf.build({})
    assert bf.contains("x") is False


# ── contains ─────────────────────────────────────────────────────────────────────

def test_contains_members():
    m = {f"k{i}": i for i in range(500)}
    bf = BloomierFilter(seed=0)
    bf.build(m)
    assert all(bf.contains(k) for k in m)


def test_contains_non_member_mostly_false():
    bf = BloomierFilter(fingerprint_bits=8, seed=0)
    bf.build({f"k{i}": i for i in range(2000)})
    fp = sum(1 for i in range(10000) if bf.contains(f"absent-{i}"))
    assert fp / 10000 < 0.02


def test_contains_dunder():
    bf = BloomierFilter(seed=0)
    bf.build({"a": 1})
    assert "a" in bf


# ── not-built / reset ────────────────────────────────────────────────────────────

def test_get_before_build_raises():
    with pytest.raises(BloomierError):
        BloomierFilter(seed=0).get("x")


def test_contains_before_build_raises():
    with pytest.raises(BloomierError):
        BloomierFilter(seed=0).contains("x")


def test_reset_returns_to_unbuilt():
    bf = BloomierFilter(seed=0)
    bf.build({"a": 1})
    bf.reset()
    assert bf.built is False
    with pytest.raises(BloomierError):
        bf.get("a")


def test_reset_reconfigures_seed_and_rebuildable():
    bf = BloomierFilter(seed=0)
    bf.build({"a": 1})
    bf.reset(seed=9)
    assert bf.seed == 9
    bf.build({"b": 2})
    assert bf.get("b") == 2


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_fingerprint_bits_zero():
    with pytest.raises(BloomierError):
        BloomierFilter(fingerprint_bits=0)


def test_invalid_fingerprint_bits_too_large():
    with pytest.raises(BloomierError):
        BloomierFilter(fingerprint_bits=64)


def test_invalid_fingerprint_bits_non_int():
    with pytest.raises(BloomierError):
        BloomierFilter(fingerprint_bits=8.5)


def test_bool_fingerprint_bits_rejected():
    with pytest.raises(BloomierError):
        BloomierFilter(fingerprint_bits=True)


def test_invalid_seed_raises():
    with pytest.raises(BloomierError):
        BloomierFilter(seed="nope")


def test_bool_seed_rejected():
    with pytest.raises(BloomierError):
        BloomierFilter(seed=True)


def test_build_non_mapping_raises():
    with pytest.raises(BloomierError):
        BloomierFilter(seed=0).build(["not", "a", "mapping"])


def test_build_duplicate_keys_raises():
    with pytest.raises(BloomierError):
        BloomierFilter(seed=0).build(_DupMapping())


def test_reset_invalid_seed_raises():
    bf = BloomierFilter(seed=0)
    with pytest.raises(BloomierError):
        bf.reset(seed="bad")


def test_error_stores_detail():
    err = BloomierError(-7)
    assert err.detail == -7
    assert "-7" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    bf = BloomierFilter(fingerprint_bits=12, seed=5)
    assert bf.fingerprint_bits == 12 and bf.seed == 5 and bf.built is False
    assert bf.num_cells == 0


def test_stats_unbuilt():
    s = BloomierFilter(fingerprint_bits=8, seed=3).stats()
    assert s["built"] is False and s["num_keys"] == 0 and s["bits_per_key"] is None
    assert s["fingerprint_bits"] == 8 and s["seed"] == 3


def test_stats_keys():
    assert set(BloomierFilter(seed=0).stats()) == {
        "built", "num_keys", "num_cells", "fingerprint_bits", "value_bits",
        "bits_per_key", "seed"}


def test_stats_after_build():
    bf = BloomierFilter(seed=0)
    bf.build({f"k{i}": i for i in range(1000)})
    s = bf.stats()
    assert s["built"] is True and s["num_keys"] == 1000
    assert s["num_cells"] > 1000 and s["bits_per_key"] is not None
    assert s["value_bits"] == (1000 - 1).bit_length()      # 10 bits to index 0..999


# ── concurrency (build once, many concurrent readers) ─────────────────────────────

def test_concurrent_gets():
    m = {f"k{i}": i for i in range(2000)}
    bf = BloomierFilter(seed=0)
    bf.build(m)
    errors = []
    mismatches = []

    def reader(base):
        try:
            for i in range(base, 2000, 10):
                if bf.get(f"k{i}") != i:
                    mismatches.append(i)
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=reader, args=(b,)) for b in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and mismatches == []
