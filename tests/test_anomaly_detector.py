"""Phase 69 — 20 tests for pradyos.core.anomaly_detector.AnomalyDetector."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.signal_aggregator import SignalAggregator
from pradyos.core.anomaly_detector import AnomalyDetector, AnomalyResult, _severity


def _detector_with(name: str, values: list[float]) -> tuple[AnomalyDetector, SignalAggregator]:
    """Build a detector whose aggregator holds ``values`` for ``name``.

    Each value is recorded one integer-second apart so every reading lands in
    its own distinct 1-second bucket (the oldest first, latest last).
    """
    sa = SignalAggregator(max_total=10000)
    now = time.time()
    n = len(values)
    for i, v in enumerate(values):
        sa.record(name, v, timestamp=now - (n - i))
    return AnomalyDetector(sa), sa


# ── init ────────────────────────────────────────────────────────────────────────

def test_init_stores_aggregator():
    sa = SignalAggregator()
    ad = AnomalyDetector(sa)
    assert ad._aggregator is sa


# ── return type ───────────────────────────────────────────────────────────────

def test_detect_returns_anomaly_result():
    ad, _ = _detector_with("cpu", [1.0, 2.0, 3.0])
    assert isinstance(ad.detect("cpu"), AnomalyResult)


# ── empty / missing signal ──────────────────────────────────────────────────────

def test_missing_signal_sample_size_zero():
    ad = AnomalyDetector(SignalAggregator())
    r = ad.detect("ghost")
    assert r.sample_size == 0
    assert r.severity == "normal"
    assert r.z_score == 0.0
    assert r.mean == 0.0
    assert r.stddev == 0.0


# ── single bucket has no spread ─────────────────────────────────────────────────

def test_single_bucket_no_spread():
    ad, _ = _detector_with("cpu", [42.0])
    r = ad.detect("cpu")
    assert r.sample_size == 1
    assert r.stddev == 0.0
    assert r.z_score == 0.0
    assert r.severity == "normal"
    assert r.mean == 42.0
    assert r.latest_value == 42.0


# ── constant signal → zero spread ───────────────────────────────────────────────

def test_constant_signal_stddev_zero():
    ad, _ = _detector_with("cpu", [7.0, 7.0, 7.0, 7.0, 7.0])
    r = ad.detect("cpu")
    assert r.sample_size == 5
    assert r.stddev == 0.0
    assert r.z_score == 0.0
    assert r.severity == "normal"


# ── clear positive anomaly → critical ───────────────────────────────────────────

def test_clear_anomaly_is_critical():
    ad, _ = _detector_with("cpu", [10.0] * 9 + [20.0])
    r = ad.detect("cpu")
    assert r.sample_size == 10
    assert r.mean == 11.0
    assert r.stddev == 3.0
    assert r.latest_value == 20.0
    assert r.z_score == 3.0
    assert r.severity == "critical"


# ── clear negative anomaly → critical (abs magnitude) ───────────────────────────

def test_negative_anomaly_is_critical():
    ad, _ = _detector_with("cpu", [20.0] * 9 + [10.0])
    r = ad.detect("cpu")
    assert r.latest_value == 10.0
    assert r.z_score == -3.0
    assert r.severity == "critical"


# ── mean / stddev / latest correctness ──────────────────────────────────────────

def test_mean_and_population_stddev():
    # buckets: 2,4,4,4,5,5,7,9 -> mean 5.0, population stddev 2.0
    ad, _ = _detector_with("g", [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    r = ad.detect("g")
    assert r.mean == 5.0
    assert r.stddev == 2.0
    assert r.latest_value == 9.0


def test_z_score_matches_formula():
    ad, _ = _detector_with("g", [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    r = ad.detect("g")
    # (9 - 5) / 2 = 2.0
    assert r.z_score == 2.0
    assert r.severity == "warning"


# ── severity thresholds via _severity ───────────────────────────────────────────

@pytest.mark.parametrize("z", [0.0, 0.5, 1.0, 1.9999, -1.5])
def test_severity_normal_band(z):
    assert _severity(z) == "normal"


@pytest.mark.parametrize("z", [2.0, 2.5, 2.9999, -2.0, -2.9])
def test_severity_warning_band(z):
    assert _severity(z) == "warning"


@pytest.mark.parametrize("z", [3.0, 4.2, 10.0, -3.0, -8.5])
def test_severity_critical_band(z):
    assert _severity(z) == "critical"


# ── 1-second bucketing collapses same-second readings ───────────────────────────

def test_same_second_readings_are_averaged():
    sa = SignalAggregator()
    base = float(int(time.time())) - 5.0  # a clean integer second, recent
    # three readings inside the SAME second -> one bucket whose value is their mean
    sa.record("cpu", 10.0, timestamp=base + 0.1)
    sa.record("cpu", 20.0, timestamp=base + 0.5)
    sa.record("cpu", 30.0, timestamp=base + 0.9)
    # a second, later bucket so we have spread
    sa.record("cpu", 60.0, timestamp=base + 1.5)
    ad = AnomalyDetector(sa)
    r = ad.detect("cpu")
    assert r.sample_size == 2          # two distinct 1-second buckets
    assert r.latest_value == 60.0      # most recent bucket
    # first bucket collapsed to mean(10,20,30)=20 -> overall mean=(20+60)/2=40
    assert r.mean == 40.0


# ── window filtering ────────────────────────────────────────────────────────────

def test_window_excludes_old_points():
    sa = SignalAggregator()
    now = time.time()
    for v in [1.0, 2.0, 3.0]:
        sa.record("cpu", v, timestamp=now - 7200)  # 2 h ago, outside 1 h window
    ad = AnomalyDetector(sa)
    r = ad.detect("cpu", window=3600.0)
    assert r.sample_size == 0
    assert r.severity == "normal"


def test_window_value_preserved():
    ad, _ = _detector_with("cpu", [1.0, 2.0, 3.0])
    r = ad.detect("cpu", window=1800.0)
    assert r.window == 1800.0


# ── rounding to 6 dp ────────────────────────────────────────────────────────────

def test_values_rounded_to_six_dp():
    ad, _ = _detector_with("g", [1.0, 2.0, 2.0])  # mean 1.666666..., irrational stddev
    r = ad.detect("g")
    for field in (r.mean, r.stddev, r.z_score, r.latest_value):
        # round(x, 6) is idempotent on an already-6dp value
        assert field == round(field, 6)


# ── to_dict shape ────────────────────────────────────────────────────────────────

def test_to_dict_has_all_keys():
    ad, _ = _detector_with("cpu", [1.0, 2.0, 3.0])
    d = ad.detect("cpu").to_dict()
    for key in ("signal", "sample_size", "window", "mean", "stddev",
                "latest_value", "z_score", "severity", "computed_at"):
        assert key in d, f"missing key: {key}"
    assert d["signal"] == "cpu"


# ── cache behaviour ──────────────────────────────────────────────────────────────

def test_cache_miss_returns_none():
    ad, _ = _detector_with("cpu", [1.0, 2.0, 3.0])
    assert ad.get_cached("cpu", 3600.0) is None


def test_cache_store_and_retrieve():
    ad, _ = _detector_with("cpu", [10.0] * 9 + [20.0])
    result = ad.detect("cpu", window=3600.0)
    ad.cache_result(result)
    hit = ad.get_cached("cpu", 3600.0)
    assert hit is result
    # a different window key must not collide
    assert ad.get_cached("cpu", 1800.0) is None


def test_lru_eviction_caps_at_128():
    ad = AnomalyDetector(SignalAggregator())
    # store 129 distinct (signal, window) keys; oldest must be evicted
    for i in range(129):
        ad.cache_result(AnomalyResult(
            signal=f"s{i}", sample_size=1, window=3600.0, mean=0.0, stddev=0.0,
            latest_value=0.0, z_score=0.0, severity="normal", computed_at=time.time(),
        ))
    assert len(ad._cache) == 128
    assert ad.get_cached("s0", 3600.0) is None     # first inserted, evicted
    assert ad.get_cached("s128", 3600.0) is not None  # last inserted, retained


# ── thread safety ────────────────────────────────────────────────────────────────

def test_concurrent_detect_and_cache_is_safe():
    ad, _ = _detector_with("cpu", [10.0] * 9 + [20.0])
    errors: list[Exception] = []
    results: list[AnomalyResult] = []

    def worker() -> None:
        try:
            for _ in range(20):
                r = ad.detect("cpu")
                ad.cache_result(r)
                ad.get_cached("cpu", 3600.0)
                results.append(r)
        except Exception as exc:  # pragma: no cover - only on a real race failure
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 30 * 20
    assert all(isinstance(r, AnomalyResult) for r in results)
    assert len(ad._cache) == 1  # all share the one (cpu, 3600.0) key
