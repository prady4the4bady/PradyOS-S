"""Tests for pradyos.campaign.analytics — CampaignAnalytics.

All tests are fully self-contained with mock registries.
No real disk I/O, no network calls.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from pradyos.campaign.model import (
    Campaign,
    CampaignNode,
    CampaignStatus,
    NodeStatus,
)
from pradyos.campaign.analytics import CampaignAnalytics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(campaigns: list[Campaign]) -> MagicMock:
    reg = MagicMock()
    reg.all.return_value = campaigns
    return reg


def _campaign(
    status: CampaignStatus = CampaignStatus.SUCCEEDED,
    created_at: float | None = None,
    started_at: float | None = None,
    finished_at: float | None = None,
    nodes: dict | None = None,
) -> Campaign:
    c = Campaign(name="test", intent="test intent")
    c.status = status
    c.created_at = created_at if created_at is not None else time.time()
    c.started_at = started_at
    c.finished_at = finished_at
    c.nodes = nodes or {}
    return c


def _node(status: NodeStatus = NodeStatus.FAILED, task_kind: str = "shell") -> CampaignNode:
    from pradyos.imperium.task import ImperiumTask
    task = ImperiumTask(kind=task_kind, intent="test")
    node = CampaignNode(task=task)
    node.status = status
    return node


# ---------------------------------------------------------------------------
# success_rate
# ---------------------------------------------------------------------------


def test_success_rate_all_succeeded():
    campaigns = [
        _campaign(CampaignStatus.SUCCEEDED),
        _campaign(CampaignStatus.SUCCEEDED),
        _campaign(CampaignStatus.SUCCEEDED),
    ]
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)
    assert a.success_rate() == 1.0


def test_success_rate_all_failed():
    campaigns = [
        _campaign(CampaignStatus.FAILED),
        _campaign(CampaignStatus.FAILED),
    ]
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)
    assert a.success_rate() == 0.0


def test_success_rate_mixed():
    campaigns = [
        _campaign(CampaignStatus.SUCCEEDED),
        _campaign(CampaignStatus.SUCCEEDED),
        _campaign(CampaignStatus.FAILED),
        _campaign(CampaignStatus.FAILED),
    ]
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)
    assert a.success_rate() == 0.5


def test_success_rate_non_terminal_ignored():
    # RUNNING and PENDING are non-terminal — not counted
    campaigns = [
        _campaign(CampaignStatus.SUCCEEDED),
        _campaign(CampaignStatus.RUNNING),  # non-terminal
        _campaign(CampaignStatus.FAILED),
    ]
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)
    # 1 succeeded out of 2 terminal
    assert a.success_rate() == 0.5


def test_success_rate_no_terminal_returns_zero():
    campaigns = [
        _campaign(CampaignStatus.RUNNING),
        _campaign(CampaignStatus.PENDING),
    ]
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)
    assert a.success_rate() == 0.0


def test_success_rate_empty_registry():
    reg = _make_registry([])
    a = CampaignAnalytics(registry=reg)
    assert a.success_rate() == 0.0


# ---------------------------------------------------------------------------
# avg_duration_s
# ---------------------------------------------------------------------------


def test_avg_duration_s_basic():
    t = time.time()
    campaigns = [
        _campaign(started_at=t, finished_at=t + 10.0),
        _campaign(started_at=t, finished_at=t + 20.0),
        _campaign(started_at=t, finished_at=t + 30.0),
    ]
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)
    assert a.avg_duration_s() == pytest.approx(20.0)


def test_avg_duration_s_skips_none_timestamps():
    t = time.time()
    campaigns = [
        _campaign(started_at=t, finished_at=t + 10.0),
        _campaign(started_at=None, finished_at=t + 20.0),  # skip: started_at None
        _campaign(started_at=t, finished_at=None),          # skip: finished_at None
        _campaign(started_at=None, finished_at=None),        # skip
    ]
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)
    assert a.avg_duration_s() == pytest.approx(10.0)


def test_avg_duration_s_no_valid_returns_zero():
    campaigns = [
        _campaign(started_at=None, finished_at=None),
    ]
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)
    assert a.avg_duration_s() == 0.0


def test_avg_duration_s_empty_returns_zero():
    reg = _make_registry([])
    a = CampaignAnalytics(registry=reg)
    assert a.avg_duration_s() == 0.0


# ---------------------------------------------------------------------------
# node_failure_histogram
# ---------------------------------------------------------------------------


def test_node_failure_histogram_basic():
    node1 = _node(NodeStatus.FAILED, "shell")
    node2 = _node(NodeStatus.FAILED, "shell")
    node3 = _node(NodeStatus.FAILED, "package")
    node4 = _node(NodeStatus.SUCCEEDED, "shell")  # not failed — excluded

    c1 = _campaign()
    c1.nodes = {"n1": node1, "n4": node4}
    c2 = _campaign()
    c2.nodes = {"n2": node2, "n3": node3}

    reg = _make_registry([c1, c2])
    a = CampaignAnalytics(registry=reg)
    hist = a.node_failure_histogram()

    assert hist["shell"] == 2
    assert hist["package"] == 1
    assert "succeeded" not in hist  # SUCCEEDED nodes don't appear


def test_node_failure_histogram_empty():
    c = _campaign()
    c.nodes = {}
    reg = _make_registry([c])
    a = CampaignAnalytics(registry=reg)
    assert a.node_failure_histogram() == {}


def test_node_failure_histogram_no_failures():
    c = _campaign()
    c.nodes = {"n1": _node(NodeStatus.SUCCEEDED)}
    reg = _make_registry([c])
    a = CampaignAnalytics(registry=reg)
    assert a.node_failure_histogram() == {}


# ---------------------------------------------------------------------------
# busiest_hours
# ---------------------------------------------------------------------------


def test_busiest_hours_ordering():
    import datetime

    # Create campaigns at specific UTC hours
    def _ts_at_hour(h: int) -> float:
        d = datetime.datetime(2025, 1, 15, h, 0, 0, tzinfo=datetime.timezone.utc)
        return d.timestamp()

    campaigns = (
        [_campaign(created_at=_ts_at_hour(9))] * 5   # 5 at 09:00
        + [_campaign(created_at=_ts_at_hour(14))] * 3  # 3 at 14:00
        + [_campaign(created_at=_ts_at_hour(3))] * 1   # 1 at 03:00
    )
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)
    result = a.busiest_hours()

    # Should be sorted by count descending
    assert result[0][0] == 9
    assert result[0][1] == 5
    assert result[1][0] == 14
    assert result[1][1] == 3
    assert result[2][0] == 3
    assert result[2][1] == 1


def test_busiest_hours_empty():
    reg = _make_registry([])
    a = CampaignAnalytics(registry=reg)
    assert a.busiest_hours() == []


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


def test_to_dict_structure():
    reg = _make_registry([])
    a = CampaignAnalytics(registry=reg)
    d = a.to_dict()

    assert "success_rate" in d
    assert "avg_duration_s" in d
    assert "node_failure_histogram" in d
    assert "busiest_hours" in d
    assert isinstance(d["success_rate"], float)
    assert isinstance(d["avg_duration_s"], float)
    assert isinstance(d["node_failure_histogram"], dict)
    assert isinstance(d["busiest_hours"], list)


def test_to_dict_values_match_individual_methods():
    t = time.time()
    node = _node(NodeStatus.FAILED, "file")
    c = _campaign(
        CampaignStatus.SUCCEEDED,
        created_at=t,
        started_at=t,
        finished_at=t + 15.0,
    )
    c.nodes = {"n1": node}

    reg = _make_registry([c])
    a = CampaignAnalytics(registry=reg)
    d = a.to_dict()

    assert d["success_rate"] == a.success_rate()
    assert d["avg_duration_s"] == a.avg_duration_s()
    assert d["node_failure_histogram"] == a.node_failure_histogram()
    assert d["busiest_hours"] == a.busiest_hours()


# ---------------------------------------------------------------------------
# last_n window
# ---------------------------------------------------------------------------


def test_last_n_limits_window():
    """Only the *last_n* most recent campaigns are included."""
    t = time.time()
    campaigns = [
        _campaign(CampaignStatus.FAILED, created_at=t - 100),
        _campaign(CampaignStatus.FAILED, created_at=t - 50),
        _campaign(CampaignStatus.SUCCEEDED, created_at=t - 1),  # most recent
    ]
    reg = _make_registry(campaigns)
    a = CampaignAnalytics(registry=reg)

    # last_n=1 → only the most recent (SUCCEEDED) → success_rate = 1.0
    assert a.success_rate(last_n=1) == 1.0

    # last_n=2 → SUCCEEDED + FAILED → success_rate = 0.5
    assert a.success_rate(last_n=2) == 0.5

    # last_n=3 → all three → SUCCEEDED + 2×FAILED → 1/3
    assert a.success_rate(last_n=3) == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# /api/analytics endpoint via TestClient
# ---------------------------------------------------------------------------


def _make_app(registry=None):
    from pradyos.sovereign_web import create_app
    return create_app(campaign_registry=registry)


def test_api_analytics_no_registry_returns_zeros():
    app = _make_app(registry=None)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success_rate"] == 0.0
    assert data["avg_duration_s"] == 0.0
    assert data["node_failure_histogram"] == {}
    assert data["busiest_hours"] == []


def test_api_analytics_with_registry():
    t = time.time()
    campaigns = [
        _campaign(CampaignStatus.SUCCEEDED, created_at=t, started_at=t, finished_at=t + 10),
        _campaign(CampaignStatus.FAILED, created_at=t - 1),
    ]
    reg = _make_registry(campaigns)
    app = _make_app(registry=reg)
    client = TestClient(app, raise_server_exceptions=True)

    resp = client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert "success_rate" in data
    assert "avg_duration_s" in data
    assert "node_failure_histogram" in data
    assert "busiest_hours" in data
    # 1 succeeded, 1 failed → 50%
    assert data["success_rate"] == pytest.approx(0.5)
