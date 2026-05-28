"""Phase 49D — 10 tests for TaskQueue endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.task_queue import TaskQueue
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_tq():
    return TestClient(create_app())


@pytest.fixture()
def client_with_tq():
    tq = TaskQueue()
    app = create_app(task_queue=tq)
    return TestClient(app), tq


# ── POST /api/v1/tasks ────────────────────────────────────────────────────────

def test_post_task_returns_fields(client_with_tq):
    client, _ = client_with_tq
    data = client.post("/api/v1/tasks",
                       json={"name": "ping", "payload": {"x": 1}}).json()
    assert data["name"] == "ping"
    assert data["status"] == "pending"
    assert data["payload"] == {"x": 1}
    assert "id" in data


def test_post_task_missing_name_400(client_with_tq):
    client, _ = client_with_tq
    resp = client.post("/api/v1/tasks", json={"payload": {}})
    assert resp.status_code == 400


def test_post_task_no_queue_400(client_no_tq):
    resp = client_no_tq.post("/api/v1/tasks", json={"name": "x"})
    assert resp.status_code == 400
    assert "error" in resp.json()


# ── GET /api/v1/tasks ─────────────────────────────────────────────────────────

def test_get_tasks_returns_tasks_and_count(client_with_tq):
    client, _ = client_with_tq
    client.post("/api/v1/tasks", json={"name": "a"})
    client.post("/api/v1/tasks", json={"name": "b"})
    data = client.get("/api/v1/tasks").json()
    assert "tasks" in data
    assert data["count"] == 2


def test_get_tasks_no_queue_empty(client_no_tq):
    data = client_no_tq.get("/api/v1/tasks").json()
    assert data["tasks"] == []
    assert data["count"] == 0


def test_get_tasks_filter_pending(client_with_tq):
    client, tq = client_with_tq
    client.post("/api/v1/tasks", json={"name": "a"})
    t2 = client.post("/api/v1/tasks", json={"name": "b"}).json()
    tq._mark_done(t2["id"], {})
    data = client.get("/api/v1/tasks?status=pending").json()
    assert data["count"] == 1


# ── GET /api/v1/tasks/{task_id} ───────────────────────────────────────────────

def test_get_task_by_id_returns_fields(client_with_tq):
    client, _ = client_with_tq
    sub = client.post("/api/v1/tasks", json={"name": "x"}).json()
    data = client.get(f"/api/v1/tasks/{sub['id']}").json()
    assert data["id"] == sub["id"]
    assert data["name"] == "x"


def test_get_task_unknown_404(client_with_tq):
    client, _ = client_with_tq
    resp = client.get("/api/v1/tasks/phantom")
    assert resp.status_code == 404


# ── DELETE /api/v1/tasks/{task_id} ────────────────────────────────────────────

def test_delete_task_cancels_pending(client_with_tq):
    client, _ = client_with_tq
    sub = client.post("/api/v1/tasks", json={"name": "x"}).json()
    resp = client.delete(f"/api/v1/tasks/{sub['id']}")
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is True


def test_delete_task_unknown_404(client_with_tq):
    client, _ = client_with_tq
    resp = client.delete("/api/v1/tasks/phantom")
    assert resp.status_code == 404
