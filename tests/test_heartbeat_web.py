"""Phase 41D — 10 tests for heartbeat endpoints in sovereign_web.

TestClient is used WITHOUT context manager (so on_event lifecycle does NOT
auto-fire — we control heartbeat state explicitly in tests).
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from pradyos.core.heartbeat import HeartbeatConfig, HeartbeatLoop
from pradyos.core.control_plane import ControlPlane
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_hb():
    return TestClient(create_app())


@pytest.fixture()
def client_with_hb():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=5.0, max_ticks=None))
    app = create_app(heartbeat=hb)
    return TestClient(app), hb


# ── GET /api/v1/heartbeat/status ──────────────────────────────────────────────

def test_get_status_returns_200(client_no_hb):
    assert client_no_hb.get("/api/v1/heartbeat/status").status_code == 200


def test_get_status_no_hb_defaults(client_no_hb):
    data = client_no_hb.get("/api/v1/heartbeat/status").json()
    assert data["running"] is False
    assert data["tick_count"] == 0


def test_get_status_with_hb_has_required_keys(client_with_hb):
    client, _ = client_with_hb
    data = client.get("/api/v1/heartbeat/status").json()
    for k in ("running", "tick_count", "interval_seconds"):
        assert k in data


def test_get_status_tick_count_zero_before_run(client_with_hb):
    client, _ = client_with_hb
    data = client.get("/api/v1/heartbeat/status").json()
    assert data["tick_count"] == 0


def test_get_status_interval_seconds_matches_config(client_with_hb):
    client, hb = client_with_hb
    data = client.get("/api/v1/heartbeat/status").json()
    assert data["interval_seconds"] == hb._config.interval_seconds


def test_custom_interval_reflected_in_status():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=2.5))
    client = TestClient(create_app(heartbeat=hb))
    data = client.get("/api/v1/heartbeat/status").json()
    assert data["interval_seconds"] == 2.5


# ── POST /api/v1/heartbeat/stop ───────────────────────────────────────────────

def test_post_stop_returns_200(client_no_hb):
    assert client_no_hb.post("/api/v1/heartbeat/stop").status_code == 200


def test_post_stop_no_hb_returns_stopped_false(client_no_hb):
    data = client_no_hb.post("/api/v1/heartbeat/stop").json()
    assert data["stopped"] is False


def test_post_stop_with_hb_returns_stopped_true(client_with_hb):
    client, _ = client_with_hb
    data = client.post("/api/v1/heartbeat/stop").json()
    assert data["stopped"] is True


# ── heartbeat + control_plane integration ────────────────────────────────────

def test_heartbeat_drives_control_plane_via_async():
    cp = ControlPlane()
    hb = HeartbeatLoop(control_plane=cp,
                       config=HeartbeatConfig(interval_seconds=0.001, max_ticks=3))

    async def run():
        await hb.start()
        await hb._task

    asyncio.run(run())
    assert hb.status()["tick_count"] == 3
