"""Tests for the Experience Distribution Tracker (T-Digest + DDSketch percentiles)."""

from __future__ import annotations

import threading

import pytest

from pradyos.core.experience_distribution import (
    ExperienceDistribution,
    ExperienceDistributionError,
)


def _ed(**kw) -> ExperienceDistribution:
    return ExperienceDistribution(seed=0, **kw)


def _fill(ed, metric="latency", n=100):
    for v in range(1, n + 1):
        ed.observe(metric, float(v))


# ── construction / validation ─────────────────────────────────────────────────


def test_default_construction():
    s = _ed().stats()
    assert s["num_metrics"] == 0 and s["total_observations"] == 0


def test_preregister_metrics():
    ed = ExperienceDistribution(metrics=["a", "b"], seed=0)
    assert ed.list_metrics() == ["a", "b"]


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 2])
def test_invalid_alpha(bad):
    with pytest.raises(ExperienceDistributionError):
        ExperienceDistribution(alpha=bad)


def test_invalid_compression():
    with pytest.raises(ExperienceDistributionError):
        ExperienceDistribution(compression=0)


# ── observe ────────────────────────────────────────────────────────────────────


def test_observe_auto_creates_metric():
    ed = _ed()
    assert "cpu" not in ed.list_metrics()
    ed.observe("cpu", 12.0)
    assert "cpu" in ed.list_metrics()


def test_observe_requires_metric_string():
    ed = _ed()
    with pytest.raises(ExperienceDistributionError):
        ed.observe("", 1.0)


def test_observe_requires_number():
    ed = _ed()
    with pytest.raises(ExperienceDistributionError):
        ed.observe("m", "not-a-number")


def test_observe_accepts_int_and_float():
    ed = _ed()
    ed.observe("m", 5)
    ed.observe("m", 5.5)
    assert ed.stats()["metrics"]["m"] == 2


def test_observe_counts_total():
    ed = _ed()
    _fill(ed, "a", 10)
    _fill(ed, "b", 5)
    assert ed.stats()["total_observations"] == 15


# ── percentile ─────────────────────────────────────────────────────────────────


def test_percentile_median():
    ed = _ed()
    _fill(ed)
    assert abs(ed.percentile("latency", 0.5) - 50.5) < 3


def test_percentile_p90():
    ed = _ed()
    _fill(ed)
    assert abs(ed.percentile("latency", 0.9) - 90) < 5


def test_percentile_monotonic():
    ed = _ed()
    _fill(ed)
    qs = [ed.percentile("latency", q) for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.99)]
    assert qs == sorted(qs)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.5, 1.5])
def test_percentile_q_validation(bad):
    ed = _ed()
    _fill(ed)
    with pytest.raises(ExperienceDistributionError):
        ed.percentile("latency", bad)


def test_percentile_unknown_metric_raises():
    with pytest.raises(ExperienceDistributionError):
        _ed().percentile("ghost", 0.5)


# ── anomaly ────────────────────────────────────────────────────────────────────


def test_anomaly_typical_value_low():
    ed = _ed()
    _fill(ed)
    assert ed.anomaly_score("latency", 50.0) < 0.3


def test_anomaly_outlier_high():
    ed = _ed()
    _fill(ed)
    assert ed.anomaly_score("latency", 999.0) > 3


def test_anomaly_outlier_dominates_normal():
    ed = _ed()
    _fill(ed)
    assert ed.anomaly_score("latency", 999.0) > ed.anomaly_score("latency", 50.0) * 5


def test_anomaly_is_nonnegative():
    ed = _ed()
    _fill(ed)
    for v in (1.0, 50.0, 100.0, 500.0):
        assert ed.anomaly_score("latency", v) >= 0.0


def test_anomaly_unknown_metric_raises():
    with pytest.raises(ExperienceDistributionError):
        _ed().anomaly_score("ghost", 1.0)


def test_anomaly_requires_number():
    ed = _ed()
    _fill(ed)
    with pytest.raises(ExperienceDistributionError):
        ed.anomaly_score("latency", "big")


# ── summary ────────────────────────────────────────────────────────────────────


def test_summary_keys_and_order():
    ed = _ed()
    _fill(ed)
    s = ed.distribution_summary("latency")
    for k in ("count", "min", "p25", "p50", "p75", "p90", "p99", "max"):
        assert k in s
    asc = [s["min"], s["p25"], s["p50"], s["p75"], s["p90"], s["p99"], s["max"]]
    assert asc == sorted(asc)


def test_summary_count():
    ed = _ed()
    _fill(ed, n=42)
    assert ed.distribution_summary("latency")["count"] == 42


def test_summary_includes_ddsketch_crosscheck():
    ed = _ed()
    _fill(ed)
    assert ed.distribution_summary("latency")["ddsketch_p50"] is not None


def test_summary_unknown_raises():
    with pytest.raises(ExperienceDistributionError):
        _ed().distribution_summary("ghost")


# ── determinism / threads / reset / metrics ────────────────────────────────────


def test_determinism():
    e1, e2 = ExperienceDistribution(seed=3), ExperienceDistribution(seed=3)
    for e in (e1, e2):
        for v in [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5]:
            e.observe("m", float(v))
    assert e1.distribution_summary("m") == e2.distribution_summary("m")


def test_concurrent_observe_no_loss():
    ed = _ed()

    def worker(b):
        for i in range(200):
            ed.observe("shared", float(b * 1000 + i))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ed.stats()["metrics"]["shared"] == 1600


def test_list_metrics_sorted():
    ed = _ed()
    for m in ("zeta", "alpha", "mu"):
        ed.observe(m, 1.0)
    assert ed.list_metrics() == ["alpha", "mu", "zeta"]


def test_reset_clears():
    ed = _ed()
    _fill(ed)
    ed.reset()
    assert ed.list_metrics() == [] and ed.stats()["total_observations"] == 0


def test_handles_zero_and_negative_values():
    # DDSketch is positive-only; the tracker must still accept 0 / negatives
    # (via T-Digest) without raising — a real bug the concurrent test caught.
    ed = _ed()
    for v in [-50.0, -1.0, 0.0, 1.0, 50.0, 100.0]:
        ed.observe("delta", v)
    assert ed.stats()["metrics"]["delta"] == 6
    assert ed.percentile("delta", 0.5) <= 50.0
    # summary works; ddsketch cross-check reflects only the positive subset
    assert ed.distribution_summary("delta")["min"] <= -1.0


def test_all_negative_metric_has_no_ddsketch_crosscheck():
    ed = _ed()
    for v in [-3.0, -2.0, -1.0]:
        ed.observe("neg", v)
    assert ed.distribution_summary("neg")["ddsketch_p50"] is None


def test_multiple_metrics_independent():
    ed = _ed()
    for v in range(1, 11):
        ed.observe("low", float(v))
    for v in range(100, 111):
        ed.observe("high", float(v))
    assert ed.percentile("low", 0.5) < ed.percentile("high", 0.5)
