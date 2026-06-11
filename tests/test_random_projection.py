"""Phase 127 — unit tests for RandomProjection / JL sketch (pradyos/core/random_projection.py)."""
from __future__ import annotations

import math
import random
import threading

import pytest

from pradyos.core.random_projection import RandomProjection, RandomProjectionError


D = 200


def _rvec(rng):
    return [rng.gauss(0, 1) for _ in range(D)]


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _norm(a):
    return math.sqrt(sum(x * x for x in a))


# ── projection shape ───────────────────────────────────────────────────────────

def test_projection_output_dim():
    rp = RandomProjection(input_dim=D, output_dim=64, seed=0)
    assert len(rp.project(_rvec(random.Random(1)))) == 64


def test_self_distance_zero():
    rp = RandomProjection(input_dim=D, output_dim=64, seed=0)
    v = _rvec(random.Random(1))
    assert rp.distance(v, v) < 1e-9


# ── JL preservation ─────────────────────────────────────────────────────────────

def test_distance_preservation():
    rp = RandomProjection(input_dim=D, output_dim=64, seed=0)
    rng = random.Random(7)
    pairs = [(_rvec(rng), _rvec(rng)) for _ in range(400)]
    ratios = [rp.distance(a, b) / _dist(a, b) for a, b in pairs]
    mean_ratio = sum(ratios) / len(ratios)
    within = sum(1 for r in ratios if 0.7 < r < 1.3) / len(ratios)
    assert abs(mean_ratio - 1.0) < 0.05
    assert within > 0.85


def test_norm_preservation():
    rp = RandomProjection(input_dim=D, output_dim=64, seed=0)
    rng = random.Random(7)
    ratios = [rp.norm(v) / _norm(v) for v in (_rvec(rng) for _ in range(400))]
    assert abs(sum(ratios) / len(ratios) - 1.0) < 0.05


def test_dot_preservation_unbiased():
    rp = RandomProjection(input_dim=D, output_dim=64, seed=0)
    rng = random.Random(7)
    pairs = [(_rvec(rng), _rvec(rng)) for _ in range(200)]
    errs = [abs(rp.dot(a, b) - sum(x * y for x, y in zip(a, b))) for a, b in pairs]
    typ = sum(_norm(a) * _norm(b) for a, b in pairs) / len(pairs)
    assert sum(errs) / len(errs) < 0.35 * typ


def test_larger_k_lowers_distortion():
    rng = random.Random(7)
    pairs = [(_rvec(rng), _rvec(rng)) for _ in range(300)]

    def ratio_std(k):
        p = RandomProjection(input_dim=D, output_dim=k, seed=0)
        rs = [p.distance(a, b) / _dist(a, b) for a, b in pairs]
        m = sum(rs) / len(rs)
        return math.sqrt(sum((r - m) ** 2 for r in rs) / len(rs))

    assert ratio_std(128) < ratio_std(16)


# ── determinism ──────────────────────────────────────────────────────────────────

def test_deterministic_projection():
    v = _rvec(random.Random(1))
    a = RandomProjection(input_dim=D, output_dim=32, seed=5)
    b = RandomProjection(input_dim=D, output_dim=32, seed=5)
    assert a.project(v) == b.project(v)


def test_different_seed_diverges():
    v = _rvec(random.Random(1))
    a = RandomProjection(input_dim=D, output_dim=32, seed=5)
    c = RandomProjection(input_dim=D, output_dim=32, seed=6)
    assert a.project(v) != c.project(v)


# ── validation ────────────────────────────────────────────────────────────────────

def test_invalid_input_dim_raises():
    with pytest.raises(RandomProjectionError):
        RandomProjection(input_dim=0)


def test_invalid_output_dim_raises():
    with pytest.raises(RandomProjectionError):
        RandomProjection(output_dim=0)


def test_invalid_seed_raises():
    with pytest.raises(RandomProjectionError):
        RandomProjection(seed="nope")


def test_bool_input_dim_rejected():
    with pytest.raises(RandomProjectionError):
        RandomProjection(input_dim=True)


def test_wrong_dimension_vector_raises():
    with pytest.raises(RandomProjectionError):
        RandomProjection(input_dim=4, output_dim=2, seed=0).project([1, 2, 3])


def test_non_numeric_vector_raises():
    with pytest.raises(RandomProjectionError):
        RandomProjection(input_dim=3, output_dim=2, seed=0).project([1, "two", 3])


def test_distance_wrong_dim_raises():
    rp = RandomProjection(input_dim=4, output_dim=2, seed=0)
    with pytest.raises(RandomProjectionError):
        rp.distance([1, 2, 3, 4], [1, 2, 3])


def test_error_stores_detail():
    err = RandomProjectionError(-3)
    assert err.detail == -3 and "-3" in str(err)


# ── properties & stats ───────────────────────────────────────────────────────────

def test_properties():
    rp = RandomProjection(input_dim=256, output_dim=32, seed=7)
    assert rp.input_dim == 256 and rp.output_dim == 32 and rp.seed == 7


def test_stats_keys():
    assert set(RandomProjection(input_dim=128, output_dim=16, seed=0).stats()) == {
        "input_dim", "output_dim", "compression_ratio", "seed"}


def test_stats_compression_ratio():
    s = RandomProjection(input_dim=128, output_dim=16, seed=3).stats()
    assert s["compression_ratio"] == 8.0 and s["seed"] == 3


# ── reset ──────────────────────────────────────────────────────────────────────────

def test_reset_reconfigures():
    rp = RandomProjection(input_dim=128, output_dim=16, seed=0)
    rp.reset(input_dim=64, output_dim=8, seed=9)
    assert rp.input_dim == 64 and rp.output_dim == 8 and rp.seed == 9
    assert len(rp.project([1.0] * 64)) == 8


def test_reset_invalid_raises():
    rp = RandomProjection(input_dim=128, output_dim=16, seed=0)
    with pytest.raises(RandomProjectionError):
        rp.reset(output_dim=0)


def test_reset_same_seed_reproduces():
    rp = RandomProjection(input_dim=16, output_dim=4, seed=5)
    v = [float(i) for i in range(16)]
    before = rp.project(v)
    rp.reset(seed=5)
    assert rp.project(v) == before


# ── algebraic identities ─────────────────────────────────────────────────────────────

def test_projection_is_linear():
    # R(a + b) == R(a) + R(b)  (the projection is a linear map).
    rp = RandomProjection(input_dim=D, output_dim=32, seed=2)
    rng = random.Random(11)
    a, b = _rvec(rng), _rvec(rng)
    ra, rb = rp.project(a), rp.project(b)
    rab = rp.project([x + y for x, y in zip(a, b)])
    assert all(math.isclose(s, x + y, rel_tol=1e-9, abs_tol=1e-9)
               for s, x, y in zip(rab, ra, rb))


def test_projection_scaling():
    # R(c·v) == c·R(v).
    rp = RandomProjection(input_dim=D, output_dim=32, seed=2)
    v = _rvec(random.Random(12))
    rv = rp.project(v)
    rcv = rp.project([3.5 * x for x in v])
    assert all(math.isclose(s, 3.5 * x, rel_tol=1e-9, abs_tol=1e-9)
               for s, x in zip(rcv, rv))


def test_zero_vector_projects_to_zero():
    rp = RandomProjection(input_dim=D, output_dim=32, seed=2)
    assert rp.project([0.0] * D) == [0.0] * 32
    assert rp.norm([0.0] * D) == 0.0


def test_dot_self_equals_norm_squared():
    rp = RandomProjection(input_dim=D, output_dim=64, seed=2)
    v = _rvec(random.Random(13))
    assert math.isclose(rp.dot(v, v), rp.norm(v) ** 2, rel_tol=1e-9, abs_tol=1e-9)


def test_dot_symmetric():
    rp = RandomProjection(input_dim=D, output_dim=64, seed=2)
    rng = random.Random(14)
    a, b = _rvec(rng), _rvec(rng)
    assert math.isclose(rp.dot(a, b), rp.dot(b, a), rel_tol=1e-9, abs_tol=1e-9)


def test_distance_symmetric():
    rp = RandomProjection(input_dim=D, output_dim=64, seed=2)
    rng = random.Random(15)
    a, b = _rvec(rng), _rvec(rng)
    assert math.isclose(rp.distance(a, b), rp.distance(b, a), rel_tol=1e-9, abs_tol=1e-9)


def test_triangle_inequality():
    # The sketch lives in real k-space, so its Euclidean distance is a true metric.
    rp = RandomProjection(input_dim=D, output_dim=64, seed=2)
    rng = random.Random(16)
    a, b, c = _rvec(rng), _rvec(rng), _rvec(rng)
    assert rp.distance(a, c) <= rp.distance(a, b) + rp.distance(b, c) + 1e-9


def test_basis_vector_components_are_rademacher():
    # Projecting the j-th standard basis vector yields column j of R, whose every
    # entry is ±1/√k by construction.
    k = 16
    rp = RandomProjection(input_dim=8, output_dim=k, seed=4)
    e0 = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    col = rp.project(e0)
    mag = 1.0 / math.sqrt(k)
    assert all(abs(abs(x) - mag) < 1e-12 for x in col)


# ── extra validation & introspection ─────────────────────────────────────────────────

def test_negative_seed_allowed():
    rp = RandomProjection(input_dim=16, output_dim=4, seed=-7)
    assert rp.seed == -7 and len(rp.project([1.0] * 16)) == 4


def test_vector_accepts_tuple():
    rp = RandomProjection(input_dim=4, output_dim=2, seed=0)
    assert len(rp.project((1.0, 2.0, 3.0, 4.0))) == 2


def test_compression_ratio_non_integer():
    s = RandomProjection(input_dim=10, output_dim=4, seed=0).stats()
    assert s["compression_ratio"] == 2.5


def test_dot_wrong_dim_raises():
    rp = RandomProjection(input_dim=4, output_dim=2, seed=0)
    with pytest.raises(RandomProjectionError):
        rp.dot([1, 2, 3, 4], [1, 2, 3])


# ── concurrency ─────────────────────────────────────────────────────────────────────

def test_concurrent_projects():
    rp = RandomProjection(input_dim=32, output_dim=8, seed=0)
    errors = []
    out = []

    def worker():
        try:
            for i in range(200):
                out.append(rp.project([float(i % 10)] * 32))
        except Exception as exc:               # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert all(len(p) == 8 for p in out)
