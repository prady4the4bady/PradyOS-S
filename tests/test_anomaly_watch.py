"""Phase 71 — unit tests for AnomalyWatch (IsolationForest watchdog)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.anomaly_watch import (
    MIN_SAMPLES,
    AnomalyWatch,
    SourceNotFoundError,
)


# A tight, deterministic "normal" baseline and a wildly separated outlier value
# keep the Isolation Forest verdicts robust regardless of internal randomness.
NORMAL = [10, 11, 9, 10, 11, 9, 10, 11, 9, 10, 11]
OUTLIER = 1_000_000.0


# ── registration ────────────────────────────────────────────────────────────

def test_register_and_sources_listed_sorted():
    w = AnomalyWatch()
    w.register_source("beta", lambda: 1.0)
    w.register_source("alpha", lambda: 2.0)
    assert w.sources() == ["alpha", "beta"]


def test_has_source():
    w = AnomalyWatch()
    assert not w.has_source("svc")
    w.register_source("svc", lambda: 1.0)
    assert w.has_source("svc")


def test_register_replaces_existing():
    w = AnomalyWatch()
    w.register_source("svc", lambda: 1.0, baseline=[1.0, 2.0, 3.0])
    assert w.sample_count("svc") == 3
    w.register_source("svc", lambda: 9.0)  # replace, no baseline
    assert w.sample_count("svc") == 0
    assert w.sources() == ["svc"]


def test_register_rejects_non_callable():
    w = AnomalyWatch()
    with pytest.raises(TypeError):
        w.register_source("svc", 123)  # type: ignore[arg-type]


def test_register_with_empty_baseline_starts_warming():
    w = AnomalyWatch()
    w.register_source("svc", lambda: 5.0, baseline=[])
    assert w.sample_count("svc") == 0
    assert w.tick()["svc"]["status"] == "warming_up"


# ── warming up vs scoring ─────────────────────────────────────────────────────

def test_tick_warming_up_before_min_samples():
    w = AnomalyWatch()
    w.register_source("svc", lambda: 1.0)
    last = None
    for _ in range(MIN_SAMPLES - 1):
        last = w.tick()["svc"]
    assert last["status"] == "warming_up"
    assert last["samples"] == MIN_SAMPLES - 1


def test_tick_scores_after_min_samples():
    w = AnomalyWatch()
    w.register_source("svc", lambda: 1.0)
    result = None
    for _ in range(MIN_SAMPLES):
        result = w.tick()["svc"]
    assert result["status"] == "scored"
    assert "anomaly" in result and "score" in result
    assert result["samples"] == MIN_SAMPLES


def test_baseline_seeds_window_so_one_tick_scores():
    w = AnomalyWatch()
    w.register_source("svc", lambda: 10.0, baseline=NORMAL)  # 11 seeded
    result = w.tick()["svc"]
    assert result["status"] == "scored"
    assert result["samples"] == len(NORMAL) + 1


def test_min_samples_is_configurable():
    w = AnomalyWatch(min_samples=3)
    w.register_source("svc", lambda: 1.0)
    assert w.tick()["svc"]["status"] == "warming_up"  # 1
    assert w.tick()["svc"]["status"] == "warming_up"  # 2
    assert w.tick()["svc"]["status"] == "scored"      # 3


# ── anomaly detection ─────────────────────────────────────────────────────────

def test_anomaly_detected_for_extreme_value():
    w = AnomalyWatch()
    w.register_source("svc", lambda: OUTLIER, baseline=[10.0] * 20)
    result = w.tick()["svc"]
    assert result["status"] == "scored"
    assert result["anomaly"] is True
    assert result["value"] == OUTLIER


def test_normal_value_not_flagged():
    w = AnomalyWatch()
    w.register_source("svc", lambda: 10.0, baseline=NORMAL)
    result = w.tick()["svc"]
    assert result["status"] == "scored"
    assert result["anomaly"] is False


def test_get_anomalies_only_returns_flagged():
    w = AnomalyWatch()
    w.register_source("bad", lambda: OUTLIER, baseline=[10.0] * 20)
    w.register_source("good", lambda: 10.0, baseline=NORMAL)
    w.tick()
    anomalies = w.get_anomalies()
    assert "bad" in anomalies
    assert "good" not in anomalies


def test_get_anomalies_empty_when_all_normal():
    w = AnomalyWatch()
    w.register_source("good", lambda: 10.0, baseline=NORMAL)
    w.tick()
    assert w.get_anomalies() == {}


def test_score_value_is_rounded():
    w = AnomalyWatch()
    w.register_source("svc", lambda: 10.123456789, baseline=NORMAL)
    result = w.tick()["svc"]
    assert result["value"] == round(10.123456789, 6)


# ── status snapshots ──────────────────────────────────────────────────────────

def test_get_status_returns_all_sources_after_tick():
    w = AnomalyWatch()
    w.register_source("a", lambda: 1.0)
    w.register_source("b", lambda: 2.0)
    w.tick()
    assert sorted(w.get_status()) == ["a", "b"]


def test_get_status_empty_before_first_tick():
    w = AnomalyWatch()
    w.register_source("a", lambda: 1.0)
    assert w.get_status() == {}


def test_get_status_returns_copies():
    w = AnomalyWatch()
    w.register_source("a", lambda: 1.0)
    w.tick()
    snap = w.get_status()
    snap["a"]["status"] = "tampered"
    assert w.get_status()["a"]["status"] != "tampered"


# ── tick mechanics ────────────────────────────────────────────────────────────

def test_tick_with_no_sources_returns_empty():
    assert AnomalyWatch().tick() == {}


def test_metric_fn_exception_is_isolated():
    w = AnomalyWatch()

    def boom() -> float:
        raise RuntimeError("sensor offline")

    w.register_source("bad", boom)
    w.register_source("good", lambda: 1.0)
    results = w.tick()  # must not raise
    assert results["bad"]["status"] == "error"
    assert "sensor offline" in results["bad"]["error"]
    assert results["good"]["status"] == "warming_up"


def test_window_is_bounded():
    w = AnomalyWatch(min_samples=5, window=12, n_estimators=10)
    w.register_source("svc", lambda: 1.0)
    for _ in range(50):
        w.tick()
    assert w.sample_count("svc") == 12


def test_sample_count_tracks_ticks():
    w = AnomalyWatch()
    w.register_source("svc", lambda: 1.0)
    w.tick()
    w.tick()
    assert w.sample_count("svc") == 2


def test_sample_count_unknown_raises():
    with pytest.raises(SourceNotFoundError):
        AnomalyWatch().sample_count("ghost")


# ── clear ─────────────────────────────────────────────────────────────────────

def test_clear_removes_all_state():
    w = AnomalyWatch()
    w.register_source("a", lambda: OUTLIER, baseline=[10.0] * 20)
    w.tick()
    w.clear()
    assert w.sources() == []
    assert w.get_status() == {}
    assert w.get_anomalies() == {}


# ── deregister (SourceNotFoundError — the CycleError-equivalent) ───────────────

def test_deregister_removes_source():
    w = AnomalyWatch()
    w.register_source("svc", lambda: 1.0)
    w.deregister("svc")
    assert not w.has_source("svc")


def test_deregister_unknown_raises_source_not_found():
    w = AnomalyWatch()
    with pytest.raises(SourceNotFoundError):
        w.deregister("ghost")


def test_source_not_found_carries_name():
    w = AnomalyWatch()
    try:
        w.deregister("ghost")
    except SourceNotFoundError as exc:
        assert exc.name == "ghost"
        assert "ghost" in str(exc)
    else:  # pragma: no cover
        pytest.fail("expected SourceNotFoundError")


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_register_and_tick_is_thread_safe():
    w = AnomalyWatch(n_estimators=10)
    errors: list[Exception] = []

    def worker(idx: int) -> None:
        try:
            w.register_source(f"svc{idx}", lambda: float(idx), baseline=[float(idx)] * 12)
            for _ in range(3):
                w.tick()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(w.sources()) == 10
    assert len(w.get_status()) == 10
