"""Phase 44D — 10 tests for execution endpoints in sovereign_web."""
from __future__ import annotations

import sys
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from pradyos.core.execution_engine import ExecutionEngine, ExecutionStatus
from pradyos.core.approval_queue import ApprovalEntry, ApprovalQueue, ApprovalStatus
from pradyos.sovereign_web import create_app


PYBIN = sys.executable.replace("\\", "/")


def _approved_entry(action: str) -> ApprovalEntry:
    return ApprovalEntry(
        id=uuid.uuid4().hex,
        action=action,
        risk_level="low",
        payload={},
        reason=None,
        status=ApprovalStatus.APPROVED,
        requested_at=time.time(),
    )


def _pending_entry(action: str) -> ApprovalEntry:
    return ApprovalEntry(
        id=uuid.uuid4().hex,
        action=action,
        risk_level="low",
        payload={},
        reason=None,
        status=ApprovalStatus.PENDING,
        requested_at=time.time(),
    )


@pytest.fixture()
def client_no_engine():
    return TestClient(create_app())


@pytest.fixture()
def client_with_engine():
    queue = ApprovalQueue()
    engine = ExecutionEngine(allowlist=[PYBIN], approval_queue=queue)
    app = create_app(approval_queue=queue, execution_engine=engine)
    return TestClient(app), queue, engine


# ── status ────────────────────────────────────────────────────────────────────

def test_get_status_returns_200(client_no_engine):
    assert client_no_engine.get("/api/v1/execute/status").status_code == 200


def test_status_no_engine_defaults(client_no_engine):
    data = client_no_engine.get("/api/v1/execute/status").json()
    assert data["total_runs"] == 0
    assert data["allowlist"] == []


# ── POST execute ──────────────────────────────────────────────────────────────

def test_post_execute_no_engine_returns_400(client_no_engine):
    resp = client_no_engine.post(f"/api/v1/execute/{uuid.uuid4().hex}")
    assert resp.status_code == 400


def test_post_execute_unknown_entry_returns_404(client_with_engine):
    client, _, _ = client_with_engine
    resp = client.post(f"/api/v1/execute/{uuid.uuid4().hex}")
    assert resp.status_code == 404


def test_post_execute_pending_entry_blocked(client_with_engine):
    client, queue, _ = client_with_engine
    entry = _pending_entry(f'{PYBIN} -c "print(1)"')
    queue._entries[entry.id] = entry
    data = client.post(f"/api/v1/execute/{entry.id}").json()
    assert data["status"] == "blocked"


def test_post_execute_approved_in_allowlist_success(client_with_engine):
    client, queue, _ = client_with_engine
    entry = _approved_entry(f'{PYBIN} -c "print(\'hi\')"')
    queue._entries[entry.id] = entry
    data = client.post(f"/api/v1/execute/{entry.id}").json()
    assert data["status"] == "success"


def test_post_execute_result_has_entry_id(client_with_engine):
    client, queue, _ = client_with_engine
    entry = _approved_entry(f'{PYBIN} -c "print(\'x\')"')
    queue._entries[entry.id] = entry
    data = client.post(f"/api/v1/execute/{entry.id}").json()
    assert data["entry_id"] == entry.id


# ── history ───────────────────────────────────────────────────────────────────

def test_get_history_returns_200(client_no_engine):
    assert client_no_engine.get("/api/v1/execute/history").status_code == 200


def test_history_no_engine_empty(client_no_engine):
    data = client_no_engine.get("/api/v1/execute/history").json()
    assert data["results"] == []


def test_history_after_run_has_one_item(client_with_engine):
    client, queue, _ = client_with_engine
    entry = _approved_entry(f'{PYBIN} -c "print(\'x\')"')
    queue._entries[entry.id] = entry
    client.post(f"/api/v1/execute/{entry.id}")
    data = client.get("/api/v1/execute/history").json()
    assert len(data["results"]) == 1
