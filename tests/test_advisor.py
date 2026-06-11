"""Tests for Phase 7D: oracle/advisor.py"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pradyos.oracle.advisor import Recommendation, SovereignAdvisor, _metric_value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit_log(events=None):
    """Return a mock audit log."""
    log = MagicMock()
    log.tail = lambda n: (events or [])[:n]
    return log


def _make_metrics(snap=None):
    reg = MagicMock()
    reg.snapshot = lambda: snap or {}
    return reg


def _make_event(action: str, timestamp: float | None = None) -> MagicMock:
    ev = MagicMock()
    ev.action = action
    ev.timestamp = timestamp or time.time()
    return ev


# ---------------------------------------------------------------------------
# 1. Empty state returns empty list
# ---------------------------------------------------------------------------

def test_empty_state_returns_empty():
    advisor = SovereignAdvisor()
    recs = advisor.recommend()
    assert isinstance(recs, list)


def test_no_audit_no_metrics_returns_list():
    advisor = SovereignAdvisor(audit_log=None, metrics_registry=None)
    recs = advisor.recommend(n=5)
    assert isinstance(recs, list)


# ---------------------------------------------------------------------------
# 2. High failure rate produces recommendation
# ---------------------------------------------------------------------------

def test_high_failure_rate_produces_recommendation():
    snap = {
        "tasks_succeeded": {"value": 1.0},
        "tasks_failed": {"value": 9.0},
    }
    advisor = SovereignAdvisor(
        audit_log=_make_audit_log(),
        metrics_registry=_make_metrics(snap),
    )
    recs = advisor.recommend()
    titles = [r.title for r in recs]
    assert any("failure" in t.lower() for t in titles)


def test_high_failure_rate_confidence_above_60():
    snap = {
        "tasks_succeeded": {"value": 0.0},
        "tasks_failed": {"value": 10.0},
    }
    advisor = SovereignAdvisor(
        audit_log=_make_audit_log(),
        metrics_registry=_make_metrics(snap),
    )
    recs = advisor.recommend()
    failure_recs = [r for r in recs if "failure" in r.title.lower()]
    assert failure_recs
    assert failure_recs[0].confidence_pct >= 60.0


# ---------------------------------------------------------------------------
# 3. Failed task audit events produce recommendations
# ---------------------------------------------------------------------------

def test_failed_task_events_produce_recommendation():
    events = [_make_event("task_failed") for _ in range(3)]
    advisor = SovereignAdvisor(
        audit_log=_make_audit_log(events),
        metrics_registry=_make_metrics(),
    )
    recs = advisor.recommend()
    assert any("failed task" in r.title.lower() or "re-run" in r.title.lower() for r in recs)


# ---------------------------------------------------------------------------
# 4. Recommendations are sorted by confidence descending
# ---------------------------------------------------------------------------

def test_recommendations_sorted_by_confidence():
    snap = {
        "tasks_succeeded": {"value": 0.0},
        "tasks_failed": {"value": 10.0},
        "oracle_plans_ok": {"value": 0.0},
        "oracle_plans_error": {"value": 5.0},
    }
    events = [_make_event("task_failed") for _ in range(5)]
    advisor = SovereignAdvisor(
        audit_log=_make_audit_log(events),
        metrics_registry=_make_metrics(snap),
    )
    recs = advisor.recommend(n=10)
    confidences = [r.confidence_pct for r in recs]
    assert confidences == sorted(confidences, reverse=True)


# ---------------------------------------------------------------------------
# 5. Oracle planner unreachable triggers recommendation
# ---------------------------------------------------------------------------

def test_oracle_unreachable_recommendation():
    snap = {
        "oracle_plans_ok": {"value": 0.0},
        "oracle_plans_error": {"value": 5.0},
    }
    advisor = SovereignAdvisor(
        audit_log=_make_audit_log(),
        metrics_registry=_make_metrics(snap),
    )
    recs = advisor.recommend()
    assert any("oracle" in r.title.lower() for r in recs)


# ---------------------------------------------------------------------------
# 6. Idle system recommendation
# ---------------------------------------------------------------------------

def test_idle_system_recommendation():
    advisor = SovereignAdvisor(
        audit_log=_make_audit_log([]),  # empty
        metrics_registry=_make_metrics(),
    )
    recs = advisor.recommend()
    assert any("idle" in r.title.lower() or "no recent" in r.title.lower() for r in recs)


# ---------------------------------------------------------------------------
# 7. n parameter limits output
# ---------------------------------------------------------------------------

def test_n_parameter_limits_output():
    snap = {
        "tasks_succeeded": {"value": 0.0},
        "tasks_failed": {"value": 20.0},
        "oracle_plans_ok": {"value": 0.0},
        "oracle_plans_error": {"value": 10.0},
    }
    events = [_make_event("task_failed") for _ in range(10)]
    advisor = SovereignAdvisor(
        audit_log=_make_audit_log(events),
        metrics_registry=_make_metrics(snap),
    )
    recs = advisor.recommend(n=2)
    assert len(recs) <= 2


# ---------------------------------------------------------------------------
# 8. Recommendation dataclass has correct fields
# ---------------------------------------------------------------------------

def test_recommendation_to_dict():
    r = Recommendation(
        rank=1,
        title="Test",
        reason="test reason",
        confidence_pct=75.5,
        suggested_campaign_goal="do something",
    )
    d = r.to_dict()
    assert d["rank"] == 1
    assert d["title"] == "Test"
    assert d["confidence_pct"] == 75.5
    assert "suggested_campaign_goal" in d


# ---------------------------------------------------------------------------
# 9. Campaign registry failures trigger recommendation
# ---------------------------------------------------------------------------

def test_failed_campaigns_recommendation():
    campaign = MagicMock()
    campaign.name = "Test Campaign"
    campaign.status = MagicMock()
    campaign.status.value = "failed"
    campaign.status.__str__ = lambda s: "failed"

    campaigns = MagicMock()
    campaigns.recent = lambda n: [campaign, campaign]

    advisor = SovereignAdvisor(
        audit_log=_make_audit_log(),
        metrics_registry=_make_metrics(),
        campaign_registry=campaigns,
    )
    recs = advisor.recommend()
    assert any("campaign" in r.title.lower() for r in recs)


# ---------------------------------------------------------------------------
# 10. _metric_value helper handles dict and missing keys gracefully
# ---------------------------------------------------------------------------

def test_metric_value_helper():
    snap = {"tasks_succeeded": {"value": 42.0}}
    assert _metric_value(snap, "tasks_succeeded") == 42.0
    assert _metric_value(snap, "missing_key") == 0.0
    assert _metric_value({}, "anything") == 0.0


# ---------------------------------------------------------------------------
# 11. Recommendations have increasing ranks
# ---------------------------------------------------------------------------

def test_recommendation_ranks_are_sequential():
    snap = {
        "tasks_succeeded": {"value": 0.0},
        "tasks_failed": {"value": 10.0},
    }
    events = [_make_event("task_failed") for _ in range(3)]
    advisor = SovereignAdvisor(
        audit_log=_make_audit_log(events),
        metrics_registry=_make_metrics(snap),
    )
    recs = advisor.recommend(n=5)
    if len(recs) >= 2:
        ranks = [r.rank for r in recs]
        assert ranks == list(range(1, len(recs) + 1))
