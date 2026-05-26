"""Phase 18D — Ledger web endpoint tests (10 tests).

FastAPI TestClient for:
  GET  /api/v1/ledger
  GET  /api/v1/ledger/verify

Covers:
  1.  GET /api/v1/ledger returns 200
  2.  response has "entries" and "count" keys
  3.  count == len(entries)
  4.  ?limit=1 returns at most 1 entry
  5.  ?service=sovereign filters by service
  6.  GET /api/v1/ledger/verify returns 200
  7.  verify response has "valid" and "count" keys
  8.  valid == True for intact ledger
  9.  No ledger injected -> safe empty (entries=[], count=0)
 10.  No ledger injected -> verify returns valid=True, count=0
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.ledger import EventLedger
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_with_ledger(ledger: EventLedger) -> TestClient:
    app = create_app(ledger=ledger)
    return TestClient(app)


def _client_no_ledger() -> TestClient:
    app = create_app()
    return TestClient(app)


def _populated_ledger() -> EventLedger:
    ledger = EventLedger()
    ledger.append(service="sovereign", event="boot")
    ledger.append(service="titan", event="op.started", payload={"task": "t1"})
    ledger.append(service="sovereign", event="task.dispatched")
    return ledger


# ===========================================================================
# Test 1: GET /api/v1/ledger returns 200
# ===========================================================================

def test_get_ledger_returns_200():
    client = _client_with_ledger(_populated_ledger())
    resp = client.get("/api/v1/ledger")
    assert resp.status_code == 200


# ===========================================================================
# Test 2: response has "entries" and "count" keys
# ===========================================================================

def test_get_ledger_response_has_required_keys():
    client = _client_with_ledger(_populated_ledger())
    data = client.get("/api/v1/ledger").json()
    assert "entries" in data
    assert "count" in data


# ===========================================================================
# Test 3: count == len(entries)
# ===========================================================================

def test_get_ledger_count_matches_entries_length():
    client = _client_with_ledger(_populated_ledger())
    data = client.get("/api/v1/ledger").json()
    assert data["count"] == len(data["entries"])


# ===========================================================================
# Test 4: ?limit=1 returns at most 1 entry
# ===========================================================================

def test_get_ledger_limit_param():
    client = _client_with_ledger(_populated_ledger())
    data = client.get("/api/v1/ledger?limit=1").json()
    assert len(data["entries"]) <= 1


# ===========================================================================
# Test 5: ?service=sovereign filters by service
# ===========================================================================

def test_get_ledger_service_filter():
    client = _client_with_ledger(_populated_ledger())
    data = client.get("/api/v1/ledger?service=sovereign").json()
    assert all(e["service"] == "sovereign" for e in data["entries"])
    assert data["count"] == len(data["entries"])


# ===========================================================================
# Test 6: GET /api/v1/ledger/verify returns 200
# ===========================================================================

def test_get_ledger_verify_returns_200():
    client = _client_with_ledger(_populated_ledger())
    resp = client.get("/api/v1/ledger/verify")
    assert resp.status_code == 200


# ===========================================================================
# Test 7: verify response has "valid" and "count" keys
# ===========================================================================

def test_get_ledger_verify_has_required_keys():
    client = _client_with_ledger(_populated_ledger())
    data = client.get("/api/v1/ledger/verify").json()
    assert "valid" in data
    assert "count" in data


# ===========================================================================
# Test 8: valid == True for intact ledger
# ===========================================================================

def test_get_ledger_verify_valid_for_intact_chain():
    client = _client_with_ledger(_populated_ledger())
    data = client.get("/api/v1/ledger/verify").json()
    assert data["valid"] is True
    assert data["count"] == 3


# ===========================================================================
# Test 9: No ledger injected -> safe empty (entries=[], count=0)
# ===========================================================================

def test_get_ledger_no_ledger_injected_safe_empty():
    client = _client_no_ledger()
    data = client.get("/api/v1/ledger").json()
    assert data["entries"] == []
    assert data["count"] == 0


# ===========================================================================
# Test 10: No ledger injected -> verify returns valid=True, count=0
# ===========================================================================

def test_get_ledger_verify_no_ledger_injected_safe():
    client = _client_no_ledger()
    data = client.get("/api/v1/ledger/verify").json()
    assert data["valid"] is True
    assert data["count"] == 0
