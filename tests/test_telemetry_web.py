"""Phase 16D — Telemetry web endpoint tests (10 tests).

FastAPI TestClient for:
  GET /api/v1/telemetry

Covers:
  1.  GET /api/v1/telemetry returns HTTP 200
  2.  Response has "spans" key
  3.  Response has "count" key
  4.  spans is a list
  5.  count equals len(spans)
  6.  ?limit=1 returns at most 1 span
  7.  ?service=sovereign filters by service
  8.  ?status=ok filters by status
  9.  count reflects filter result
 10.  No telemetry injected -> {"spans": [], "count": 0}
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.telemetry import TelemetryCollector
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client(telemetry: TelemetryCollector | None = None) -> TestClient:
    app = create_app(telemetry=telemetry)
    return TestClient(app)


def _populated_collector() -> TelemetryCollector:
    col = TelemetryCollector()
    col.record("campaign.run", "sovereign", status="ok")
    col.record("task.dispatch", "imperium", status="ok")
    col.record("heal.trigger", "sovereign", status="error")
    return col


# ===========================================================================
# Test 1: GET /api/v1/telemetry returns HTTP 200
# ===========================================================================

def test_get_telemetry_returns_200():
    client = _client(_populated_collector())
    resp = client.get("/api/v1/telemetry")
    assert resp.status_code == 200


# ===========================================================================
# Test 2: Response has "spans" key
# ===========================================================================

def test_response_has_spans_key():
    client = _client(_populated_collector())
    data = client.get("/api/v1/telemetry").json()
    assert "spans" in data


# ===========================================================================
# Test 3: Response has "count" key
# ===========================================================================

def test_response_has_count_key():
    client = _client(_populated_collector())
    data = client.get("/api/v1/telemetry").json()
    assert "count" in data


# ===========================================================================
# Test 4: spans is a list
# ===========================================================================

def test_spans_is_list():
    client = _client(_populated_collector())
    data = client.get("/api/v1/telemetry").json()
    assert isinstance(data["spans"], list)


# ===========================================================================
# Test 5: count equals len(spans)
# ===========================================================================

def test_count_equals_len_spans():
    client = _client(_populated_collector())
    data = client.get("/api/v1/telemetry").json()
    assert data["count"] == len(data["spans"])


# ===========================================================================
# Test 6: ?limit=1 returns at most 1 span
# ===========================================================================

def test_limit_query_param():
    client = _client(_populated_collector())
    data = client.get("/api/v1/telemetry?limit=1").json()
    assert len(data["spans"]) <= 1


# ===========================================================================
# Test 7: ?service=sovereign filters by service
# ===========================================================================

def test_service_filter():
    client = _client(_populated_collector())
    data = client.get("/api/v1/telemetry?service=sovereign").json()
    assert all(s["service"] == "sovereign" for s in data["spans"])


# ===========================================================================
# Test 8: ?status=ok filters by status
# ===========================================================================

def test_status_filter():
    client = _client(_populated_collector())
    data = client.get("/api/v1/telemetry?status=ok").json()
    assert all(s["status"] == "ok" for s in data["spans"])


# ===========================================================================
# Test 9: count reflects filter result
# ===========================================================================

def test_count_reflects_filter():
    client = _client(_populated_collector())
    data = client.get("/api/v1/telemetry?service=sovereign").json()
    assert data["count"] == len(data["spans"])


# ===========================================================================
# Test 10: No telemetry injected -> {"spans": [], "count": 0}
# ===========================================================================

def test_no_telemetry_returns_empty():
    client = _client(telemetry=None)
    data = client.get("/api/v1/telemetry").json()
    assert data == {"spans": [], "count": 0}
