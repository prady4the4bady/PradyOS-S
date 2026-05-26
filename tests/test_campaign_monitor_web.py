"""Phase 13 — GET /api/v1/campaigns/monitor endpoint tests (10 tests).

Uses FastAPI TestClient to exercise the campaign monitor HTTP endpoint
wired into the sovereign web app via the ``campaign_monitor`` parameter
of ``create_app()``.

Covers:
    1.  HTTP 200
    2.  keys: active_campaigns, step_timeline, titan_ops_feed
    3.  active_campaigns is a list
    4.  step_timeline is a list
    5.  titan_ops_feed is a list
    6.  active_campaigns reflects injected registry
    7.  Content-Type application/json
    8.  step_timeline entries have ts field
    9.  titan_ops_feed entries have topic field
    10. endpoint returns 200 even when no monitor injected (safe fallback)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from pradyos.aurora_throne.campaign_monitor import (
    CampaignMonitor,
    CampaignMonitorSnapshot,
)
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(
    active_campaigns: list | None = None,
    step_timeline: list | None = None,
    titan_ops_feed: list | None = None,
) -> CampaignMonitorSnapshot:
    return CampaignMonitorSnapshot(
        active_campaigns=active_campaigns or [],
        step_timeline=step_timeline or [],
        titan_ops_feed=titan_ops_feed or [],
    )


def _make_monitor_mock(snapshot: CampaignMonitorSnapshot) -> MagicMock:
    mon = MagicMock(spec=CampaignMonitor)
    mon.get_snapshot.return_value = snapshot
    return mon


def _client(snapshot: CampaignMonitorSnapshot | None = None) -> TestClient:
    """Create a TestClient with an optional mock CampaignMonitor."""
    mon_mock = _make_monitor_mock(snapshot) if snapshot is not None else None
    app = create_app(campaign_monitor=mon_mock)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Test 1: HTTP 200
# ---------------------------------------------------------------------------

def test_monitor_endpoint_returns_200():
    client = _client(_make_snapshot())
    resp = client.get("/api/v1/campaigns/monitor")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 2: keys: active_campaigns, step_timeline, titan_ops_feed
# ---------------------------------------------------------------------------

def test_monitor_response_has_required_keys():
    client = _client(_make_snapshot())
    data = client.get("/api/v1/campaigns/monitor").json()
    assert "active_campaigns" in data
    assert "step_timeline" in data
    assert "titan_ops_feed" in data


# ---------------------------------------------------------------------------
# Test 3: active_campaigns is a list
# ---------------------------------------------------------------------------

def test_monitor_active_campaigns_is_list():
    client = _client(_make_snapshot())
    data = client.get("/api/v1/campaigns/monitor").json()
    assert isinstance(data["active_campaigns"], list)


# ---------------------------------------------------------------------------
# Test 4: step_timeline is a list
# ---------------------------------------------------------------------------

def test_monitor_step_timeline_is_list():
    client = _client(_make_snapshot())
    data = client.get("/api/v1/campaigns/monitor").json()
    assert isinstance(data["step_timeline"], list)


# ---------------------------------------------------------------------------
# Test 5: titan_ops_feed is a list
# ---------------------------------------------------------------------------

def test_monitor_titan_ops_feed_is_list():
    client = _client(_make_snapshot())
    data = client.get("/api/v1/campaigns/monitor").json()
    assert isinstance(data["titan_ops_feed"], list)


# ---------------------------------------------------------------------------
# Test 6: active_campaigns reflects injected registry
# ---------------------------------------------------------------------------

def test_monitor_active_campaigns_reflects_registry():
    campaigns = [
        {"campaign_id": "c-web-1", "name": "Alpha Deployment", "status": "running"},
        {"campaign_id": "c-web-2", "name": "Beta Rollout", "status": "planning"},
    ]
    snap = _make_snapshot(active_campaigns=campaigns)
    client = _client(snap)
    data = client.get("/api/v1/campaigns/monitor").json()
    ids = [c["campaign_id"] for c in data["active_campaigns"]]
    assert "c-web-1" in ids
    assert "c-web-2" in ids


# ---------------------------------------------------------------------------
# Test 7: Content-Type application/json
# ---------------------------------------------------------------------------

def test_monitor_returns_json_content_type():
    client = _client(_make_snapshot())
    resp = client.get("/api/v1/campaigns/monitor")
    assert "application/json" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Test 8: step_timeline entries have ts field
# ---------------------------------------------------------------------------

def test_monitor_step_timeline_entries_have_ts():
    timeline = [
        {"campaign_id": "c-t1", "step": "build", "status": "ok", "ts": 1748000000.0},
        {"campaign_id": "c-t2", "step": "deploy", "status": "ok", "ts": 1748000001.0},
    ]
    snap = _make_snapshot(step_timeline=timeline)
    client = _client(snap)
    data = client.get("/api/v1/campaigns/monitor").json()
    for entry in data["step_timeline"]:
        assert "ts" in entry


# ---------------------------------------------------------------------------
# Test 9: titan_ops_feed entries have topic field
# ---------------------------------------------------------------------------

def test_monitor_titan_ops_feed_entries_have_topic():
    titan_feed = [
        {"topic": "titan.shell_exec", "payload": {"task_id": "tx-1"}, "ts": 1748000000.0},
        {"topic": "titan.rollback", "payload": {"task_id": "tx-2"}, "ts": 1748000001.0},
    ]
    snap = _make_snapshot(titan_ops_feed=titan_feed)
    client = _client(snap)
    data = client.get("/api/v1/campaigns/monitor").json()
    for entry in data["titan_ops_feed"]:
        assert "topic" in entry


# ---------------------------------------------------------------------------
# Test 10: endpoint returns 200 even when no monitor injected (safe fallback)
# ---------------------------------------------------------------------------

def test_monitor_endpoint_200_when_no_monitor_injected():
    app = create_app()  # no campaign_monitor
    client = TestClient(app)
    resp = client.get("/api/v1/campaigns/monitor")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_campaigns"] == []
    assert data["step_timeline"] == []
    assert data["titan_ops_feed"] == []
