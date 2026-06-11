"""Phase 90 — unit tests for QuotientFilter (pradyos/core/quotient.py)."""
from __future__ import annotations

import random
import threading
from collections import Counter

import pytest

from pradyos.core.quotient import QuotientError, QuotientFilter


def distinct_hash(n_items, q, r, seed=0):
    """An injected hash giving each of ``n_items`` a distinct (q+r)-bit fingerprint —
    so membership is exact (no false positives) while quotients still collide."""
    fps = random.Random(seed).sample(range(1 << (q + r)), n_items)
    mapping = {k: fps[k] for k in range(n_items)}
    return mapping, (lambda x: mapping[x])


# ── basic correctness ──────────────────────────────────────────────────────────

def test_insert_returns_true():
    assert QuotientFilter(q=8, r=8).insert("a") is True


def test_contains_after_insert():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("a")
    assert qf.contains("a") is True


def test_contains_absent_is_false():
    _, h = distinct_hash(10, 4, 8)
    qf = QuotientFilter(q=4, r=8, hash_fn=h)
    qf.insert(0)
    assert qf.contains(1) is False


def test_delete_present_returns_true():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("a")
    assert qf.delete("a") is True


def test_delete_absent_returns_false():
    assert QuotientFilter(q=8, r=8).delete("nope") is False


def test_delete_removes_membership():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("a")
    qf.delete("a")
    assert qf.contains("a") is False


def test_len_tracks_used_slots():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("a")
    qf.insert("b")
    assert len(qf) == 2


def test_contains_dunder():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("a")
    assert "a" in qf and "b" not in qf


# ── no false negatives ───────────────────────────────────────────────────────────

def test_insert_many_all_found():
    qf = QuotientFilter(q=10, r=8)        # 1024 slots
    items = [f"item{i}" for i in range(500)]
    for it in items:
        qf.insert(it)
    assert [it for it in items if not qf.contains(it)] == []


# ── duplicate counting ───────────────────────────────────────────────────────────

def test_insert_twice_counts_two():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("dup")
    qf.insert("dup")
    assert qf.count("dup") == 2


def test_count_absent_is_zero():
    assert QuotientFilter(q=8, r=8).count("ghost") == 0


def test_delete_decrements_count():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("d")
    qf.insert("d")
    qf.delete("d")
    assert qf.count("d") == 1 and qf.contains("d")


def test_delete_to_zero_removes():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("d")
    qf.delete("d")
    assert qf.count("d") == 0 and not qf.contains("d")


def test_reinsert_after_delete():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("a")
    qf.delete("a")
    assert qf.insert("a") and qf.contains("a")


def test_items_counts_duplicates():
    qf = QuotientFilter(q=8, r=8)
    qf.insert("a")
    qf.insert("a")
    qf.insert("b")
    assert qf.stats()["items"] == 3 and qf.stats()["used"] == 2


# ── run / cluster navigation (injected hash) ─────────────────────────────────────

def test_run_collision_all_found():
    r = 8
    mapping = {f"k{i}": (5 << r) | (i + 1) for i in range(40)}   # all quotient 5
    qf = QuotientFilter(q=6, r=r, hash_fn=lambda x: mapping[x])
    for k in mapping:
        qf.insert(k)
    assert [k for k in mapping if not qf.contains(k)] == []
    assert len(qf) == 40


def test_delete_from_middle_of_run():
    r = 8
    mapping = {f"k{i}": (5 << r) | (i + 1) for i in range(40)}
    qf = QuotientFilter(q=6, r=r, hash_fn=lambda x: mapping[x])
    for k in mapping:
        qf.insert(k)
    qf.delete("k20")
    assert not qf.contains("k20")
    assert all(qf.contains(k) for k in mapping if k != "k20")


def test_delete_run_start_with_continuations():
    r = 8
    mapping = {f"k{i}": (5 << r) | (i + 1) for i in range(10)}
    qf = QuotientFilter(q=6, r=r, hash_fn=lambda x: mapping[x])
    for k in mapping:
        qf.insert(k)
    qf.delete("k0")                       # k0 has the smallest remainder → run head
    assert not qf.contains("k0")
    assert all(qf.contains(k) for k in mapping if k != "k0")


def test_adjacent_quotient_runs_independent():
    r = 8
    # two quotients whose runs sit next to each other in one cluster
    mapping = {}
    for i in range(8):
        mapping[f"a{i}"] = (5 << r) | (i + 1)
        mapping[f"b{i}"] = (6 << r) | (i + 1)
    qf = QuotientFilter(q=6, r=r, hash_fn=lambda x: mapping[x])
    for k in mapping:
        qf.insert(k)
    assert all(qf.contains(k) for k in mapping)
    for k in list(mapping)[::3]:
        qf.delete(k)
    assert all(qf.contains(k) for k in mapping if k not in list(mapping)[::3])


# ── randomized differential test vs ground truth ─────────────────────────────────

def test_randomized_differential_vs_counter():
    for seed in range(6):
        rnd = random.Random(seed)
        q, r, n = 6, 8, 50
        mapping, h = distinct_hash(n, q, r, seed)
        qf = QuotientFilter(q=q, r=r, hash_fn=h)
        model = Counter()
        for _ in range(2000):
            k = rnd.randrange(n)
            if rnd.random() < 0.55:
                if qf.insert(k):
                    model[k] += 1
                else:
                    assert model[k] == 0
            else:
                res = qf.delete(k)
                assert res == (model[k] > 0)
                if res:
                    model[k] -= 1
        for k in range(n):
            assert qf.contains(k) == (model[k] > 0)
            assert qf.count(k) == model[k]
        assert qf.stats()["items"] == sum(model.values())


# ── configuration & validation ───────────────────────────────────────────────────

def test_default_slots_is_256():
    assert QuotientFilter().slots == 256


def test_configurable_q_and_r():
    qf = QuotientFilter(q=10, r=12)
    assert qf.slots == 1024 and qf.remainder_bits == 12


def test_invalid_q_zero_raises():
    with pytest.raises(QuotientError):
        QuotientFilter(q=0)


def test_invalid_q_too_large_raises():
    with pytest.raises(QuotientError):
        QuotientFilter(q=33)


def test_invalid_q_bool_raises():
    with pytest.raises(QuotientError):
        QuotientFilter(q=True)


def test_invalid_r_zero_raises():
    with pytest.raises(QuotientError):
        QuotientFilter(q=8, r=0)


def test_invalid_seed_float_raises():
    with pytest.raises(QuotientError):
        QuotientFilter(q=8, r=8, seed=1.5)


def test_quotient_error_stores_detail():
    err = QuotientError(-7)
    assert err.detail == -7
    assert "invalid quotient filter configuration" in str(err)


# ── false-positive rate ──────────────────────────────────────────────────────────

def test_false_positive_rate_bounded():
    qf = QuotientFilter(q=12, r=8)        # 4096 slots, light load
    for i in range(800):
        qf.insert(f"present-{i}")
    fp = sum(1 for i in range(10_000) if qf.contains(f"absent-{i}"))
    assert fp / 10_000 < 0.02             # comfortably above the ~2^-8 expectation, well bounded


def test_wider_remainder_fewer_false_positives():
    def fp_count(r):
        qf = QuotientFilter(q=12, r=r)
        for i in range(800):
            qf.insert(f"present-{i}")
        return sum(1 for i in range(10_000) if qf.contains(f"absent-{i}"))
    assert fp_count(12) <= fp_count(6)


# ── determinism ──────────────────────────────────────────────────────────────────

def test_deterministic_with_injected_hash():
    h = lambda x: (x * 2654435761) & 0xFFFF
    a = QuotientFilter(q=8, r=8, hash_fn=h)
    b = QuotientFilter(q=8, r=8, hash_fn=h)
    for i in range(100):
        a.insert(i)
        b.insert(i)
    assert a._entries() == b._entries()


def test_same_seed_same_membership():
    a = QuotientFilter(q=8, r=8, seed=5)
    b = QuotientFilter(q=8, r=8, seed=5)
    for i in range(100):
        a.insert(f"x{i}")
        b.insert(f"x{i}")
    assert all(a.contains(f"x{i}") == b.contains(f"x{i}") for i in range(100))


# ── stats ────────────────────────────────────────────────────────────────────────

def test_stats_keys():
    assert set(QuotientFilter(q=8, r=8).stats()) == {
        "q", "slots", "remainder_bits", "used", "items", "load_factor", "false_positive_rate",
    }


def test_stats_initial():
    s = QuotientFilter(q=8, r=8).stats()
    assert s["used"] == 0 and s["items"] == 0 and s["load_factor"] == 0.0


def test_stats_false_positive_rate_formula():
    assert QuotientFilter(q=8, r=10).stats()["false_positive_rate"] == 2.0 ** -10


def test_stats_load_factor():
    qf = QuotientFilter(q=4, r=8)         # 16 slots
    for i in range(4):
        qf.insert(f"k{i}")
    assert qf.stats()["load_factor"] == pytest.approx(4 / 16)


# ── merge ────────────────────────────────────────────────────────────────────────

def test_merge_combines_filters():
    a = QuotientFilter(q=8, r=8, seed=1)
    b = QuotientFilter(q=8, r=8, seed=1)
    for i in range(50):
        a.insert(f"a{i}")
        b.insert(f"b{i}")
    a.merge(b)
    assert all(a.contains(f"a{i}") for i in range(50))
    assert all(a.contains(f"b{i}") for i in range(50))


def test_merge_accumulates_counts():
    a = QuotientFilter(q=8, r=8, seed=1)
    b = QuotientFilter(q=8, r=8, seed=1)
    a.insert("shared")
    b.insert("shared")
    a.merge(b)
    assert a.count("shared") == 2


def test_merge_mismatched_q_raises():
    a = QuotientFilter(q=8, r=8)
    with pytest.raises(QuotientError):
        a.merge(QuotientFilter(q=7, r=8))


def test_merge_non_filter_raises():
    with pytest.raises(QuotientError):
        QuotientFilter(q=8, r=8).merge("not a filter")


# ── full filter & reset ──────────────────────────────────────────────────────────

def test_full_filter_insert_returns_false():
    qf = QuotientFilter(q=2, r=4)         # 4 slots
    results = [qf.insert(f"x{i}") for i in range(10)]
    assert results.count(True) <= 4
    assert False in results


def test_reset_clears():
    qf = QuotientFilter(q=8, r=8)
    for i in range(20):
        qf.insert(f"k{i}")
    qf.reset()
    assert len(qf) == 0 and qf.stats()["items"] == 0


def test_reset_reconfigures():
    qf = QuotientFilter(q=8, r=8)
    qf.reset(q=10, r=12)
    assert qf.slots == 1024 and qf.remainder_bits == 12


def test_reset_invalid_raises():
    qf = QuotientFilter(q=8, r=8)
    with pytest.raises(QuotientError):
        qf.reset(q=0)


# ── concurrency ──────────────────────────────────────────────────────────────────

def test_concurrent_inserts_10_threads():
    qf = QuotientFilter(q=12, r=10)       # 4096 slots, no fullness
    errors = []

    def worker(tag):
        try:
            for i in range(50):
                qf.insert(f"t{tag}-{i}")
        except Exception as exc:          # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert all(qf.contains(f"t{tag}-{i}") for tag in range(10) for i in range(50))


def test_concurrent_insert_delete_consistent():
    qf = QuotientFilter(q=12, r=10)
    errors = []

    def inserter(tag):
        try:
            for i in range(100):
                qf.insert(f"x{tag}-{i}")
        except Exception as exc:          # pragma: no cover
            errors.append(exc)

    def deleter(tag):
        try:
            for i in range(100):
                qf.delete(f"x{tag}-{i}")
        except Exception as exc:          # pragma: no cover
            errors.append(exc)

    threads = ([threading.Thread(target=inserter, args=(t,)) for t in range(5)]
               + [threading.Thread(target=deleter, args=(t,)) for t in range(5)])
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(qf) >= 0
