"""Phase 68D — 10 tests for Scheduler endpoints in sovereign_web.

Uses /api/v1/jobs/* (NOT /api/v1/scheduler/* which is owned by Phases 15+38).
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pradyos.core.job_scheduler import Scheduler
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_sched():
    return TestClient(create_app())


@pytest.fixture()
def client_with_sched():
    s = Scheduler()
    s.register_handler("ping", lambda p: {"ok": True, "payload": p})
    app = create_app(job_scheduler=s)
    return TestClient(app), s


# ── POST /api/v1/jobs (schedule) ─────────────────────────────────────────────

def test_post_create_returns_200_with_job_fields(client_with_sched):
    client, _ = client_with_sched
    data = client.post("/api/v1/jobs", json={
        "name": "ping",
        "run_at": time.time() + 60,
        "payload": {"x": 1},
    }).json()
    for k in ("job_id", "name", "run_at", "status", "next_run_at"):
        assert k in data
    assert data["name"] == "ping"
    assert data["status"] == "pending"


def test_post_no_scheduler_returns_error(client_no_sched):
    data = client_no_sched.post("/api/v1/jobs", json={
        "name": "ping", "run_at": time.time(),
    }).json()
    assert "error" in data


def test_post_missing_name_400(client_with_sched):
    client, _ = client_with_sched
    resp = client.post("/api/v1/jobs", json={"run_at": time.time()})
    assert resp.status_code == 400


def test_post_missing_run_at_400(client_with_sched):
    client, _ = client_with_sched
    resp = client.post("/api/v1/jobs", json={"name": "ping"})
    assert resp.status_code == 400


# ── POST /api/v1/jobs/tick ───────────────────────────────────────────────────

def test_post_tick_executes_due_job(client_with_sched):
    client, _ = client_with_sched
    client.post("/api/v1/jobs", json={
        "name": "ping",
        "run_at": time.time() - 1,
    })
    data = client.post("/api/v1/jobs/tick", json={}).json()
    assert len(data["executed"]) == 1
    assert data["executed"][0]["status"] == "completed"


def test_post_tick_returns_executed_list(client_with_sched):
    client, _ = client_with_sched
    data = client.post("/api/v1/jobs/tick", json={}).json()
    assert "executed" in data
    assert isinstance(data["executed"], list)


# ── GET /api/v1/jobs (list) ─────────────────────────────────────────────────

def test_get_jobs_returns_jobs_key(client_with_sched):
    client, _ = client_with_sched
    client.post("/api/v1/jobs", json={
        "name": "ping", "run_at": time.time() + 60,
    })
    data = client.get("/api/v1/jobs").json()
    assert "jobs" in data
    assert len(data["jobs"]) >= 1


# ── GET /api/v1/jobs/{id} ───────────────────────────────────────────────────

def test_get_job_by_id_returns_correct_job(client_with_sched):
    client, _ = client_with_sched
    sub = client.post("/api/v1/jobs", json={
        "name": "ping", "run_at": time.time() + 60,
    }).json()
    data = client.get(f"/api/v1/jobs/{sub['job_id']}").json()
    assert data["job_id"] == sub["job_id"]


def test_get_unknown_job_404(client_with_sched):
    client, _ = client_with_sched
    resp = client.get("/api/v1/jobs/phantom-id")
    assert resp.status_code == 404


# ── DELETE /api/v1/jobs/{id} (cancel) ───────────────────────────────────────

def test_delete_pending_job_returns_cancelled_true(client_with_sched):
    client, _ = client_with_sched
    sub = client.post("/api/v1/jobs", json={
        "name": "ping", "run_at": time.time() + 999,
    }).json()
    resp = client.delete(f"/api/v1/jobs/{sub['job_id']}")
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is True
