"""Phase 15D — Scheduler web endpoint tests (10 tests).

FastAPI TestClient for:
  GET    /api/v1/scheduler/jobs
  POST   /api/v1/scheduler/jobs
  DELETE /api/v1/scheduler/jobs/{job_id}
  POST   /api/v1/scheduler/jobs/{job_id}/enable
  POST   /api/v1/scheduler/jobs/{job_id}/disable

Covers:
  1.  GET /api/v1/scheduler/jobs returns HTTP 200
  2.  GET response has "jobs" key
  3.  "jobs" value is a list
  4.  POST /api/v1/scheduler/jobs returns HTTP 200
  5.  POST response has all required job keys
  6.  GET after POST reflects new job
  7.  DELETE /api/v1/scheduler/jobs/{job_id} returns HTTP 200
  8.  DELETE response has "removed" key
  9.  POST enable endpoint returns {"enabled": True}
 10.  POST disable endpoint returns {"disabled": True}
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from pradyos.core.bus import EventBus
from pradyos.sovereign.scheduler import SovereignScheduler
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_JOB_KEYS = {
    "job_id", "cron_expr", "campaign_spec", "priority",
    "sla_seconds", "next_run", "enabled",
}

_SAMPLE_JOB_BODY = {
    "job_id": "web-test-job",
    "cron_expr": "* * * * *",
    "campaign_spec": {"name": "web-smoke"},
    "priority": 7,
    "sla_seconds": 60.0,
}


def _make_scheduler() -> SovereignScheduler:
    engine = MagicMock()
    bus = EventBus()
    return SovereignScheduler(campaign_engine=engine, bus=bus)


def _client(scheduler: SovereignScheduler | None = None) -> TestClient:
    app = create_app(scheduler=scheduler)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Test 1: GET /api/v1/scheduler/jobs returns HTTP 200
# ---------------------------------------------------------------------------

def test_get_jobs_returns_200():
    client = _client(_make_scheduler())
    resp = client.get("/api/v1/scheduler/jobs")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 2: GET response has "jobs" key
# ---------------------------------------------------------------------------

def test_get_jobs_response_has_jobs_key():
    client = _client(_make_scheduler())
    data = client.get("/api/v1/scheduler/jobs").json()
    assert "jobs" in data


# ---------------------------------------------------------------------------
# Test 3: "jobs" value is a list
# ---------------------------------------------------------------------------

def test_get_jobs_value_is_list():
    client = _client(_make_scheduler())
    data = client.get("/api/v1/scheduler/jobs").json()
    assert isinstance(data["jobs"], list)


# ---------------------------------------------------------------------------
# Test 4: POST /api/v1/scheduler/jobs returns HTTP 200
# ---------------------------------------------------------------------------

def test_post_job_returns_200():
    client = _client(_make_scheduler())
    resp = client.post("/api/v1/scheduler/jobs", json=_SAMPLE_JOB_BODY)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 5: POST response has all required job keys
# ---------------------------------------------------------------------------

def test_post_job_response_has_required_keys():
    client = _client(_make_scheduler())
    data = client.post("/api/v1/scheduler/jobs", json=_SAMPLE_JOB_BODY).json()
    assert _REQUIRED_JOB_KEYS.issubset(data.keys()), (
        f"Missing keys: {_REQUIRED_JOB_KEYS - data.keys()}"
    )


# ---------------------------------------------------------------------------
# Test 6: GET after POST reflects new job
# ---------------------------------------------------------------------------

def test_get_after_post_reflects_new_job():
    scheduler = _make_scheduler()
    client = _client(scheduler)

    client.post("/api/v1/scheduler/jobs", json=_SAMPLE_JOB_BODY)
    data = client.get("/api/v1/scheduler/jobs").json()

    job_ids = [j["job_id"] for j in data["jobs"]]
    assert "web-test-job" in job_ids


# ---------------------------------------------------------------------------
# Test 7: DELETE /api/v1/scheduler/jobs/{job_id} returns HTTP 200
# ---------------------------------------------------------------------------

def test_delete_job_returns_200():
    scheduler = _make_scheduler()
    client = _client(scheduler)
    client.post("/api/v1/scheduler/jobs", json=_SAMPLE_JOB_BODY)
    resp = client.delete("/api/v1/scheduler/jobs/web-test-job")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 8: DELETE response has "removed" key
# ---------------------------------------------------------------------------

def test_delete_job_response_has_removed_key():
    scheduler = _make_scheduler()
    client = _client(scheduler)
    client.post("/api/v1/scheduler/jobs", json=_SAMPLE_JOB_BODY)
    data = client.delete("/api/v1/scheduler/jobs/web-test-job").json()
    assert "removed" in data


# ---------------------------------------------------------------------------
# Test 9: POST enable endpoint returns {"enabled": True}
# ---------------------------------------------------------------------------

def test_enable_endpoint_returns_enabled_true():
    scheduler = _make_scheduler()
    client = _client(scheduler)
    client.post("/api/v1/scheduler/jobs", json=_SAMPLE_JOB_BODY)
    # Disable first, then enable
    client.post("/api/v1/scheduler/jobs/web-test-job/disable")
    data = client.post("/api/v1/scheduler/jobs/web-test-job/enable").json()
    assert data == {"enabled": True}


# ---------------------------------------------------------------------------
# Test 10: POST disable endpoint returns {"disabled": True}
# ---------------------------------------------------------------------------

def test_disable_endpoint_returns_disabled_true():
    scheduler = _make_scheduler()
    client = _client(scheduler)
    client.post("/api/v1/scheduler/jobs", json=_SAMPLE_JOB_BODY)
    data = client.post("/api/v1/scheduler/jobs/web-test-job/disable").json()
    assert data == {"disabled": True}
