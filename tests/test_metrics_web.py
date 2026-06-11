"""Phase 22D — Metrics web endpoint tests (10 tests).

FastAPI TestClient for:
  GET  /metrics
  GET  /api/v1/metrics

Covers:
 1.  GET /metrics returns 200
 2.  GET /metrics Content-Type starts with "text/plain"
 3.  GET /metrics body is non-empty
 4.  GET /metrics body contains "# HELP"
 5.  GET /api/v1/metrics returns 200
 6.  GET /api/v1/metrics returns JSON object
 7.  GET /api/v1/metrics has at least one key after increment
 8.  No metrics injected → GET /metrics returns 200 with empty body
 9.  No metrics injected → GET /api/v1/metrics returns 200 with {}
10.  GET /metrics body contains a pre-registered metric name
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.metrics_registry import MetricsRegistry
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(inject: bool = True) -> tuple[TestClient, MetricsRegistry | None]:
    if inject:
        reg = MetricsRegistry()
        app = create_app(metrics=reg)
        return TestClient(app), reg
    app = create_app()
    return TestClient(app), None


# ---------------------------------------------------------------------------
# GET /metrics — with MetricsRegistry injected
# ---------------------------------------------------------------------------

def test_metrics_returns_200() -> None:
    client, _ = _make_client()
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_content_type_is_text_plain() -> None:
    client, _ = _make_client()
    resp = client.get("/metrics")
    assert resp.headers["content-type"].startswith("text/plain")


def test_metrics_body_non_empty() -> None:
    client, _ = _make_client()
    resp = client.get("/metrics")
    assert resp.text.strip() != ""


def test_metrics_body_contains_help() -> None:
    client, _ = _make_client()
    resp = client.get("/metrics")
    assert "# HELP" in resp.text


def test_metrics_body_contains_pre_registered_name() -> None:
    client, _ = _make_client()
    resp = client.get("/metrics")
    assert "pradyos_errors_total" in resp.text


# ---------------------------------------------------------------------------
# GET /api/v1/metrics — with MetricsRegistry injected
# ---------------------------------------------------------------------------

def test_api_metrics_returns_200() -> None:
    client, _ = _make_client()
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200


def test_api_metrics_returns_json_object() -> None:
    client, _ = _make_client()
    resp = client.get("/api/v1/metrics")
    data = resp.json()
    assert isinstance(data, dict)


def test_api_metrics_has_key_after_increment() -> None:
    client, reg = _make_client()
    assert reg is not None
    reg.increment("pradyos_errors_total", 3.0)
    resp = client.get("/api/v1/metrics")
    data = resp.json()
    assert len(data) >= 1
    assert "pradyos_errors_total" in data


# ---------------------------------------------------------------------------
# No metrics injected (metrics=None)
# ---------------------------------------------------------------------------

def test_no_metrics_prometheus_returns_200_empty() -> None:
    client, _ = _make_client(inject=False)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.text == ""


def test_no_metrics_api_returns_200_empty_dict() -> None:
    client, _ = _make_client(inject=False)
    resp = client.get("/api/v1/metrics")
    assert resp.status_code == 200
    assert resp.json() == {}
