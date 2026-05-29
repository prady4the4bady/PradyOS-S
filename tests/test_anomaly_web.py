"""Phase 69 — 10 tests for the /api/v1/anomaly endpoints in sovereign_web."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pradyos.core.signal_aggregator import SignalAggregator
from pradyos.core.anomaly_detector import AnomalyDetector
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_engine():
    return TestClient(create_app())


@pytest.fixture()
def client_with_engine():
    sa = SignalAggregator(max_total=10000)
    ad = AnomalyDetector(sa)
    app = create_app(signal_aggregator=sa, anomaly_detector=ad)
    return TestClient(app), sa


def _seed(sa: SignalAggregator, name: str, values: list[float], age: float = 0.0) -> None:
    """Record ``values`` one integer-second apart, oldest first (latest last)."""
    now = time.time() - age
    n = len(values)
    for i, v in enumerate(values):
        sa.record(name, v, timestamp=now - (n - i))


# ── no engine ─────────────────────────────────────────────────────────────────

def test_get_anomaly_no_engine_returns_error(client_no_engine):
    assert "error" in client_no_engine.get("/api/v1/anomaly?signal=cpu").json()


def test_post_anomaly_no_engine_returns_error(client_no_engine):
    assert "error" in client_no_engine.post("/api/v1/anomaly", json={"signal": "cpu"}).json()


# ── valid GET ─────────────────────────────────────────────────────────────────

def test_get_anomaly_valid_returns_200(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "cpu", [10.0] * 9 + [20.0])
    assert client.get("/api/v1/anomaly?signal=cpu").status_code == 200


def test_get_anomaly_response_has_all_fields(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "cpu", [10.0] * 9 + [20.0])
    data = client.get("/api/v1/anomaly?signal=cpu").json()
    for key in ("signal", "sample_size", "window", "mean", "stddev",
                "latest_value", "z_score", "severity", "computed_at", "cached"):
        assert key in data, f"Missing key: {key}"
    assert data["severity"] == "critical"


# ── valid POST ────────────────────────────────────────────────────────────────

def test_post_anomaly_valid_returns_200(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "mem", [1.0, 2.0, 3.0])
    resp = client.post("/api/v1/anomaly", json={"signal": "mem"})
    assert resp.status_code == 200
    assert resp.json()["signal"] == "mem"


# ── unknown signal ──────────────────────────────────────────────────────────────

def test_unknown_signal_returns_sample_size_zero(client_with_engine):
    client, _ = client_with_engine
    data = client.get("/api/v1/anomaly?signal=ghost").json()
    assert data["sample_size"] == 0
    assert data["severity"] == "normal"


# ── caching ──────────────────────────────────────────────────────────────────────

def test_use_cache_first_call_is_uncached(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "cpu", [10.0] * 9 + [20.0])
    data = client.get("/api/v1/anomaly?signal=cpu&use_cache=true").json()
    assert data["cached"] is False


def test_use_cache_second_call_is_cached(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "cpu", [10.0] * 9 + [20.0])
    client.get("/api/v1/anomaly?signal=cpu&use_cache=true")          # populate cache
    data = client.get("/api/v1/anomaly?signal=cpu&use_cache=true").json()
    assert data["cached"] is True


# ── window param ──────────────────────────────────────────────────────────────

def test_window_defaults_to_3600(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "cpu", [1.0, 2.0, 3.0])
    assert client.get("/api/v1/anomaly?signal=cpu").json()["window"] == 3600.0


def test_window_filter_excludes_old_points(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "cpu", [1.0, 2.0, 3.0], age=7200.0)  # all readings 2 h old
    data = client.get("/api/v1/anomaly?signal=cpu&window=3600").json()
    assert data["sample_size"] == 0
