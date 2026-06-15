"""HTTP tests for the Sovereign Experience routes (/api/v1/experience)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _fill(c, metric="latency", n=100):
    for v in range(1, n + 1):
        c.post("/api/v1/experience/observe", json={"metric": metric, "value": float(v)})


def test_observe_creates_metric():
    c = _client()
    r = c.post("/api/v1/experience/observe", json={"metric": "cpu", "value": 12.0})
    assert r.status_code == 200 and r.json()["metrics"] == 1
    assert "cpu" in c.get("/api/v1/experience/metrics").json()["metrics"]


def test_observe_requires_fields():
    c = _client()
    assert c.post("/api/v1/experience/observe", json={"metric": "x"}).status_code == 422
    assert c.post("/api/v1/experience/observe", json={"value": 1}).status_code == 422


def test_observe_rejects_non_number():
    c = _client()
    assert c.post("/api/v1/experience/observe", json={"metric": "x", "value": "big"}).status_code == 422


def test_percentile_median():
    c = _client()
    _fill(c)
    r = c.get("/api/v1/experience/percentile", params={"metric": "latency", "q": 0.5})
    assert abs(r.json()["value"] - 50.5) < 3


def test_percentile_q_validation():
    c = _client()
    _fill(c)
    assert c.get("/api/v1/experience/percentile", params={"metric": "latency", "q": 0}).status_code == 422
    assert c.get("/api/v1/experience/percentile", params={"metric": "latency", "q": 1}).status_code == 422


def test_percentile_unknown_metric_404():
    c = _client()
    assert c.get("/api/v1/experience/percentile", params={"metric": "ghost", "q": 0.5}).status_code == 404


def test_anomaly_typical_low():
    c = _client()
    _fill(c)
    assert c.get("/api/v1/experience/anomaly", params={"metric": "latency", "value": 50.0}).json()["anomaly_score"] < 0.3


def test_anomaly_outlier_high():
    c = _client()
    _fill(c)
    assert c.get("/api/v1/experience/anomaly", params={"metric": "latency", "value": 999.0}).json()["anomaly_score"] > 3


def test_anomaly_unknown_404():
    c = _client()
    assert c.get("/api/v1/experience/anomaly", params={"metric": "ghost", "value": 1.0}).status_code == 404


def test_summary_shape_and_order():
    c = _client()
    _fill(c)
    s = c.get("/api/v1/experience/summary", params={"metric": "latency"}).json()
    asc = [s["min"], s["p25"], s["p50"], s["p75"], s["p90"], s["p99"], s["max"]]
    assert asc == sorted(asc)


def test_summary_unknown_404():
    c = _client()
    assert c.get("/api/v1/experience/summary", params={"metric": "ghost"}).status_code == 404


def test_metrics_lists_all():
    c = _client()
    c.post("/api/v1/experience/observe", json={"metric": "a", "value": 1})
    c.post("/api/v1/experience/observe", json={"metric": "b", "value": 2})
    assert set(c.get("/api/v1/experience/metrics").json()["metrics"]) == {"a", "b"}


def test_reset_clears():
    c = _client()
    _fill(c)
    assert c.post("/api/v1/experience/reset").json()["num_metrics"] == 0


def test_handles_zero_and_negative_over_http():
    c = _client()
    for v in (-5.0, 0.0, 5.0):
        assert c.post("/api/v1/experience/observe", json={"metric": "d", "value": v}).status_code == 200
    assert c.get("/api/v1/experience/metrics").json()["stats"]["metrics"]["d"] == 3


def test_each_app_isolated():
    c1, c2 = _client(), _client()
    c1.post("/api/v1/experience/observe", json={"metric": "only1", "value": 1})
    assert c1.get("/api/v1/experience/metrics").json()["metrics"] == ["only1"]
    assert c2.get("/api/v1/experience/metrics").json()["metrics"] == []
