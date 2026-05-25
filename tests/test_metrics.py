"""Tests for Phase 6 MetricsRegistry — Counter, Gauge, Histogram, snapshot, API endpoint.

Covers: counter, gauge, histogram, snapshot, API endpoint.
"""

from __future__ import annotations

import math

import pytest

from pradyos.core.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    get_registry,
    reset_registry_for_tests,
)


# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------


def test_counter_starts_at_zero():
    c = Counter("requests_total")
    assert c.value == 0.0


def test_counter_inc_default():
    c = Counter("c")
    c.inc()
    c.inc()
    assert c.value == 2.0


def test_counter_inc_custom_amount():
    c = Counter("c")
    c.inc(5)
    assert c.value == 5.0


def test_counter_inc_float():
    c = Counter("c")
    c.inc(0.5)
    c.inc(1.5)
    assert c.value == pytest.approx(2.0)


def test_counter_negative_raises():
    c = Counter("c")
    with pytest.raises(ValueError):
        c.inc(-1)


def test_counter_snapshot():
    c = Counter("req_total", "Total requests")
    c.inc(3)
    s = c.snapshot()
    assert s["type"] == "counter"
    assert s["name"] == "req_total"
    assert s["value"] == 3.0
    assert s["description"] == "Total requests"


# ---------------------------------------------------------------------------
# Gauge
# ---------------------------------------------------------------------------


def test_gauge_starts_at_zero():
    g = Gauge("mem_bytes")
    assert g.value == 0.0


def test_gauge_set():
    g = Gauge("g")
    g.set(42.5)
    assert g.value == pytest.approx(42.5)


def test_gauge_inc_positive():
    g = Gauge("g")
    g.set(10)
    g.inc(5)
    assert g.value == pytest.approx(15.0)


def test_gauge_inc_negative():
    g = Gauge("g")
    g.set(10)
    g.inc(-3)
    assert g.value == pytest.approx(7.0)


def test_gauge_snapshot():
    g = Gauge("cpu_pct", "CPU utilisation")
    g.set(55.5)
    s = g.snapshot()
    assert s["type"] == "gauge"
    assert s["value"] == pytest.approx(55.5)
    assert s["name"] == "cpu_pct"


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


def test_histogram_starts_empty():
    h = Histogram("latency")
    assert h.count == 0
    assert h.sum_ == 0.0
    assert math.isnan(h.mean)


def test_histogram_observe():
    h = Histogram("lat", buckets=[1.0, 5.0, 10.0])
    h.observe(0.5)
    h.observe(3.0)
    h.observe(8.0)
    assert h.count == 3
    assert h.sum_ == pytest.approx(11.5)
    assert h.mean == pytest.approx(11.5 / 3)


def test_histogram_bucket_overflow():
    h = Histogram("lat", buckets=[1.0, 2.0])
    h.observe(100.0)  # goes to +Inf bucket
    snap = h.snapshot()
    inf_bucket = next(b for b in snap["buckets"] if b["le"] == "+Inf")
    assert inf_bucket["count"] == 1


def test_histogram_snapshot_structure():
    h = Histogram("resp", "Response time", buckets=[0.1, 0.5, 1.0])
    h.observe(0.05)
    h.observe(0.3)
    s = h.snapshot()
    assert s["type"] == "histogram"
    assert s["name"] == "resp"
    assert s["count"] == 2
    assert s["sum"] == pytest.approx(0.35)
    assert s["mean"] == pytest.approx(0.175)
    assert any(b["le"] == "+Inf" for b in s["buckets"])


# ---------------------------------------------------------------------------
# MetricsRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_get():
    reg = MetricsRegistry()
    c = Counter("hits")
    reg.register(c)
    assert reg.get("hits") is c


def test_registry_get_missing_returns_none():
    reg = MetricsRegistry()
    assert reg.get("nope") is None


def test_registry_snapshot_empty():
    reg = MetricsRegistry()
    assert reg.snapshot() == {}


def test_registry_snapshot_all_types():
    reg = MetricsRegistry()
    c = Counter("req")
    g = Gauge("mem")
    h = Histogram("lat", buckets=[1.0])
    c.inc(10)
    g.set(256)
    h.observe(0.5)
    reg.register(c)
    reg.register(g)
    reg.register(h)
    snap = reg.snapshot()
    assert "req" in snap
    assert "mem" in snap
    assert "lat" in snap
    assert snap["req"]["type"] == "counter"
    assert snap["mem"]["type"] == "gauge"
    assert snap["lat"]["type"] == "histogram"


def test_registry_singleton():
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_registry_reset_for_tests():
    r1 = get_registry()
    r2 = reset_registry_for_tests()
    assert r1 is not r2
    r3 = get_registry()
    assert r3 is r2


# ---------------------------------------------------------------------------
# /api/metrics endpoint
# ---------------------------------------------------------------------------


def test_api_metrics_endpoint():
    """GET /api/metrics returns JSON snapshot from MetricsRegistry."""
    from fastapi.testclient import TestClient
    from pradyos.sovereign_web import create_app

    reset_registry_for_tests()
    reg = get_registry()
    c = Counter("test_api_counter", "API test counter")
    c.inc(7)
    reg.register(c)

    app = create_app()
    client = TestClient(app)
    response = client.get("/api/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert "ts" in data
    assert "test_api_counter" in data["metrics"]
    assert data["metrics"]["test_api_counter"]["value"] == pytest.approx(7.0)

    reset_registry_for_tests()
