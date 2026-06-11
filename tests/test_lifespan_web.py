"""Phase 42D — 10 tests for the lifespan migration.

Uses TestClient as a context manager so the lifespan actually fires.
"""
from __future__ import annotations

import asyncio
import warnings

import pytest
from fastapi.testclient import TestClient

from pradyos.core.heartbeat import HeartbeatConfig, HeartbeatLoop
from pradyos.sovereign_web import create_app


# ── 1. App starts without on_event deprecation ───────────────────────────────

def test_app_starts_without_deprecation_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        app = create_app()
        with TestClient(app):
            pass  # lifespan startup + shutdown both fire here


# ── 2. heartbeat starts on app startup ────────────────────────────────────────

def test_heartbeat_starts_on_app_startup():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=10.0, max_ticks=None))
    app = create_app(heartbeat=hb)
    with TestClient(app):
        # inside the context, lifespan startup has fired
        assert hb._running is True


# ── 3. heartbeat stops on app shutdown ────────────────────────────────────────

def test_heartbeat_stops_on_app_shutdown():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=10.0, max_ticks=None))
    app = create_app(heartbeat=hb)
    with TestClient(app):
        pass
    # exited the context — shutdown fired
    assert hb._running is False


# ── 4. No heartbeat → app starts cleanly ──────────────────────────────────────

def test_no_heartbeat_app_starts_cleanly():
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/heartbeat/status").status_code == 200


# ── 5. status endpoint 200 after startup ──────────────────────────────────────

def test_status_endpoint_200_after_startup():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=10.0, max_ticks=None))
    with TestClient(create_app(heartbeat=hb)) as client:
        assert client.get("/api/v1/heartbeat/status").status_code == 200


# ── 6. status shows running=True after startup ────────────────────────────────

def test_status_running_true_after_startup():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=10.0, max_ticks=None))
    with TestClient(create_app(heartbeat=hb)) as client:
        data = client.get("/api/v1/heartbeat/status").json()
        assert data["running"] is True


# ── 7. POST stop works during lifespan ────────────────────────────────────────

def test_post_stop_during_lifespan():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=10.0, max_ticks=None))
    with TestClient(create_app(heartbeat=hb)) as client:
        resp = client.post("/api/v1/heartbeat/stop")
        assert resp.status_code == 200
        assert resp.json()["stopped"] is True


# ── 8. Lifespan with max_ticks heartbeat: tick_count advances ────────────────

def test_lifespan_max_ticks_advances():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=0.001, max_ticks=3))
    with TestClient(create_app(heartbeat=hb)) as client:
        # Wait via an async sleep to let the loop iterate
        async def wait():
            await asyncio.sleep(0.05)
        asyncio.run(wait())
    # After shutdown, heartbeat has run all 3 ticks
    assert hb._tick_count == 3


# ── 9. No DeprecationWarning on app creation ─────────────────────────────────

def test_no_deprecation_warning_on_app_creation():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        create_app()
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)
                    and "on_event" in str(w.message)]
    assert deprecations == [], f"Found on_event deprecations: {deprecations}"


# ── 10. create_app() accepts heartbeat and wires lifespan ────────────────────

def test_create_app_accepts_heartbeat_param():
    hb = HeartbeatLoop(config=HeartbeatConfig(interval_seconds=10.0, max_ticks=None))
    # Should not raise
    app = create_app(heartbeat=hb)
    # Lifespan is wired — heartbeat starts when context entered
    with TestClient(app):
        assert hb._running is True
