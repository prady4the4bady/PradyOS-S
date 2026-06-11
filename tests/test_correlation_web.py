"""Phase 33D — 10 tests for correlation engine endpoints in sovereign_web."""
from __future__ import annotations

import math
import time

import pytest
from fastapi.testclient import TestClient

from pradyos.core.signal_aggregator import SignalAggregator
from pradyos.core.correlation_engine import CorrelationEngine
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_engine():
    return TestClient(create_app())


@pytest.fixture()
def client_with_engine():
    sa = SignalAggregator(max_total=10000)
    ce = CorrelationEngine(sa)
    app = create_app(signal_aggregator=sa, correlation_engine=ce)
    return TestClient(app), sa


def _seed(sa: SignalAggregator, name: str, values: list[float]) -> None:
    now = time.time()
    for i, v in enumerate(values):
        sa.record(name, v, timestamp=now - len(values) + i)


# ── no engine ─────────────────────────────────────────────────────────────────

def test_get_correlate_no_engine_returns_error(client_no_engine):
    resp = client_no_engine.get("/api/v1/correlate?signal_a=a&signal_b=b")
    assert "error" in resp.json()


def test_get_correlate_missing_params_returns_error(client_with_engine):
    client, _ = client_with_engine
    resp = client.get("/api/v1/correlate?signal_a=a")
    assert "error" in resp.json()


def test_post_correlate_no_engine_returns_error(client_no_engine):
    resp = client_no_engine.post("/api/v1/correlate",
                                  json={"signal_a": "a", "signal_b": "b"})
    assert "error" in resp.json()


def test_post_correlate_missing_params_returns_error(client_with_engine):
    client, _ = client_with_engine
    resp = client.post("/api/v1/correlate", json={"signal_a": "a"})
    assert "error" in resp.json()


# ── valid GET ─────────────────────────────────────────────────────────────────

def test_get_correlate_valid_returns_200(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "x", [1.0, 2.0, 3.0])
    _seed(sa, "y", [1.0, 2.0, 3.0])
    resp = client.get("/api/v1/correlate?signal_a=x&signal_b=y")
    assert resp.status_code == 200


def test_get_correlate_response_has_all_fields(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "x", [1.0, 2.0, 3.0])
    _seed(sa, "y", [1.0, 2.0, 3.0])
    data = client.get("/api/v1/correlate?signal_a=x&signal_b=y").json()
    for key in ("signal_a", "signal_b", "coefficient", "sample_size",
                "label", "window_secs", "computed_at"):
        assert key in data, f"Missing key: {key}"


# ── valid POST ────────────────────────────────────────────────────────────────

def test_post_correlate_valid_returns_200(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "p", [1.0, 2.0, 3.0])
    _seed(sa, "q", [1.0, 2.0, 3.0])
    resp = client.post("/api/v1/correlate", json={"signal_a": "p", "signal_b": "q"})
    assert resp.status_code == 200


def test_post_correlate_response_has_coefficient(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "p", [1.0, 2.0, 3.0])
    _seed(sa, "q", [1.0, 2.0, 3.0])
    data = client.post("/api/v1/correlate",
                       json={"signal_a": "p", "signal_b": "q"}).json()
    assert "coefficient" in data


# ── window param ──────────────────────────────────────────────────────────────

def test_window_zero_returns_sample_size_zero(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "m", [1.0, 2.0, 3.0])
    _seed(sa, "n", [1.0, 2.0, 3.0])
    data = client.get("/api/v1/correlate?signal_a=m&signal_b=n&window=0").json()
    assert data["sample_size"] == 0


# ── identical signals → coefficient=1.0 ──────────────────────────────────────

def test_identical_signals_coefficient_one(client_with_engine):
    client, sa = client_with_engine
    _seed(sa, "s1", [1.0, 2.0, 3.0, 4.0, 5.0])
    _seed(sa, "s2", [1.0, 2.0, 3.0, 4.0, 5.0])
    data = client.get("/api/v1/correlate?signal_a=s1&signal_b=s2").json()
    coeff = data["coefficient"]
    assert coeff is not None
    assert abs(coeff - 1.0) < 1e-9
