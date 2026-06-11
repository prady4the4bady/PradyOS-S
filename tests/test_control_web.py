"""Phase 40D — 10 tests for OS control plane endpoints in sovereign_web.

Uses GET /api/v1/os/control (not /status — Phase 36 owns /status) and
POST /api/v1/os/tick (new path).
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pradyos.core.control_plane import ControlPlane
from pradyos.core.scheduler import TaskScheduler
from pradyos.sovereign_web import create_app


EXPECTED_MODULES = {
    "health_scorecard", "signal_aggregator", "task_scheduler",
    "memory_store", "healing_monitor", "snapshot_store",
    "reactor_engine", "state_manager", "watchpoint_system",
    "correlation_engine", "integration_bus",
}


@pytest.fixture()
def client_no_cp():
    return TestClient(create_app())


@pytest.fixture()
def client_with_cp():
    cp = ControlPlane()
    app = create_app(control_plane=cp)
    return TestClient(app), cp


# ── GET /api/v1/os/control ────────────────────────────────────────────────────

def test_get_control_returns_200(client_no_cp):
    assert client_no_cp.get("/api/v1/os/control").status_code == 200


def test_get_control_no_cp_has_os_version(client_no_cp):
    data = client_no_cp.get("/api/v1/os/control").json()
    assert "os_version" in data


def test_get_control_no_cp_modules_empty(client_no_cp):
    data = client_no_cp.get("/api/v1/os/control").json()
    assert data["modules"] == {}


def test_get_control_with_cp_os_version_0_40_0(client_with_cp):
    client, _ = client_with_cp
    data = client.get("/api/v1/os/control").json()
    assert data["os_version"] == "0.40.0"


def test_get_control_with_cp_uptime_positive(client_with_cp):
    client, _ = client_with_cp
    time.sleep(0.001)
    data = client.get("/api/v1/os/control").json()
    assert data["uptime_seconds"] > 0


def test_get_control_with_cp_modules_has_expected_keys(client_with_cp):
    client, _ = client_with_cp
    data = client.get("/api/v1/os/control").json()
    assert set(data["modules"].keys()) == EXPECTED_MODULES


# ── POST /api/v1/os/tick ──────────────────────────────────────────────────────

def test_post_tick_returns_200(client_no_cp):
    assert client_no_cp.post("/api/v1/os/tick").status_code == 200


def test_post_tick_no_cp_all_empty(client_no_cp):
    data = client_no_cp.post("/api/v1/os/tick").json()
    assert data["ticks"] == []
    assert data["healed"] == []
    assert data["reactions"] == []


def test_post_tick_with_cp_and_scheduler_returns_ticks_key():
    ts = TaskScheduler()
    ts.register("hb", 0.001, lambda: None)
    ts._tasks["hb"].next_run_at = time.time() - 10
    cp = ControlPlane(task_scheduler=ts)
    app = create_app(control_plane=cp)
    client = TestClient(app)
    data = client.post("/api/v1/os/tick").json()
    assert "ticks" in data
    assert len(data["ticks"]) == 1


# ── full check: all 11 module names present in modules dict ──────────────────

def test_full_status_check_all_11_module_names(client_with_cp):
    client, _ = client_with_cp
    data = client.get("/api/v1/os/control").json()
    for name in EXPECTED_MODULES:
        assert name in data["modules"], f"Missing module: {name}"
        assert "present" in data["modules"][name]
        assert "summary" in data["modules"][name]
