"""Phase 38D — 10 tests for TaskScheduler endpoints in sovereign_web."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pradyos.core.scheduler import TaskScheduler
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_ts():
    return TestClient(create_app())


@pytest.fixture()
def client_with_ts():
    ts = TaskScheduler()
    app = create_app(task_scheduler=ts)
    return TestClient(app), ts


# ── GET /api/v1/scheduler/tasks ───────────────────────────────────────────────

def test_get_tasks_returns_200(client_no_ts):
    assert client_no_ts.get("/api/v1/scheduler/tasks").status_code == 200


def test_get_tasks_no_scheduler_empty(client_no_ts):
    data = client_no_ts.get("/api/v1/scheduler/tasks").json()
    assert data["tasks"] == []


# ── POST /api/v1/scheduler/tasks ──────────────────────────────────────────────

def test_post_task_returns_200(client_with_ts):
    client, _ = client_with_ts
    resp = client.post("/api/v1/scheduler/tasks",
                       json={"name": "hb", "interval_seconds": 5.0})
    assert resp.status_code == 200


def test_post_task_no_scheduler_error(client_no_ts):
    data = client_no_ts.post("/api/v1/scheduler/tasks",
                              json={"name": "hb", "interval_seconds": 1.0}).json()
    assert "error" in data


def test_post_task_response_has_required_fields(client_with_ts):
    client, _ = client_with_ts
    data = client.post("/api/v1/scheduler/tasks",
                       json={"name": "hb", "interval_seconds": 5.0}).json()
    assert data["name"] == "hb"
    assert data["interval_seconds"] == 5.0
    assert "next_run_at" in data


# ── DELETE /api/v1/scheduler/tasks/{name} ─────────────────────────────────────

def test_delete_task_returns_deleted_true(client_with_ts):
    client, ts = client_with_ts
    ts.register("hb", 1.0, lambda: None)
    resp = client.delete("/api/v1/scheduler/tasks/hb")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_delete_task_unknown_returns_404(client_with_ts):
    client, _ = client_with_ts
    resp = client.delete("/api/v1/scheduler/tasks/phantom")
    assert resp.status_code == 404


# ── POST /api/v1/scheduler/tick ───────────────────────────────────────────────

def test_post_tick_returns_200(client_no_ts):
    assert client_no_ts.post("/api/v1/scheduler/tick").status_code == 200


def test_post_tick_no_scheduler_empty(client_no_ts):
    data = client_no_ts.post("/api/v1/scheduler/tick").json()
    assert data["runs"] == []


# ── full flow ─────────────────────────────────────────────────────────────────

def test_full_flow_register_then_force_due_tick(client_with_ts):
    client, ts = client_with_ts
    client.post("/api/v1/scheduler/tasks",
                json={"name": "hb", "interval_seconds": 60.0})
    # Force the task due by directly calling tick on the scheduler with a future now.
    runs = ts.tick(now=time.time() + 9999)
    assert len(runs) == 1
    log = ts.get_log()
    assert len(log) == 1
    assert log[0].task_name == "hb"
