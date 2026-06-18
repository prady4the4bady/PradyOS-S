"""Tests for Sovereign Web Dashboard (Phase 4C).

Uses FastAPI TestClient — no live server, no live filesystem beyond tmp_path.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from pradyos.core.bus import EventBus
from pradyos.sovereign_web import _DECISIONS_FILE, _DEFAULT_STATE_DIR, create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_campaign(campaign_id: str = "camp-1", status: str = "running") -> MagicMock:
    c = MagicMock()
    c.campaign_id = campaign_id
    c.name = "Test Campaign"
    c.status = MagicMock()
    c.status.value = status
    c.to_dict.return_value = {
        "campaign_id": campaign_id,
        "name": "Test Campaign",
        "status": status,
        "intent": "do something",
        "created_at": time.time(),
        "nodes": {},
    }
    c.progress.return_value = {"running": 1}
    return c


def _make_registry(campaigns: list[Any] | None = None) -> MagicMock:
    reg = MagicMock()
    clist = campaigns or [_make_campaign()]
    reg.active.return_value = [c for c in clist if c.status.value in ("running", "planning")]
    reg.recent.return_value = clist
    return reg


def _make_checkpoint() -> MagicMock:
    cp = MagicMock(spec=[])  # spec=[] means no auto-created attributes
    cp.path = Path("/tmp/imperium_tasks.jsonl")
    return cp


# ---------------------------------------------------------------------------
# Helper: create a test app with isolated decisions file
# ---------------------------------------------------------------------------


def _test_app(tmp_path: Path) -> tuple[TestClient, Path]:
    """Return (TestClient, decisions_file_path) using tmp_path for isolation."""
    import pradyos.sovereign_web as sw

    decisions_file = tmp_path / "sovereign_decisions.jsonl"
    # Monkey-patch the module-level paths for this test
    original_dir = sw._DEFAULT_STATE_DIR
    original_file = sw._DECISIONS_FILE
    sw._DEFAULT_STATE_DIR = tmp_path
    sw._DECISIONS_FILE = decisions_file

    bus = EventBus()
    registry = _make_registry()
    checkpoint = _make_checkpoint()
    app = create_app(campaign_registry=registry, checkpoint_store=checkpoint, bus=bus)
    client = TestClient(app, raise_server_exceptions=True)

    # Restore after client creation (TestClient won't use them at runtime)
    sw._DEFAULT_STATE_DIR = original_dir
    sw._DECISIONS_FILE = original_file

    return client, decisions_file


# ---------------------------------------------------------------------------
# 1. GET / — returns HTML dashboard
# ---------------------------------------------------------------------------


def test_get_root_returns_html(tmp_path: Path) -> None:
    client, _ = _test_app(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "PradyOS" in resp.text
    assert "Sovereign" in resp.text


# ---------------------------------------------------------------------------
# 2. GET /api/status — returns correct JSON shape
# ---------------------------------------------------------------------------


def test_get_api_status(tmp_path: Path) -> None:
    client, _ = _test_app(tmp_path)
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "timestamp" in data
    assert "checkpoint" in data
    assert "warden" in data
    assert "active_campaigns" in data
    assert isinstance(data["active_campaigns"], list)


# ---------------------------------------------------------------------------
# 3. GET /api/campaigns — returns list of campaigns with progress
# ---------------------------------------------------------------------------


def test_get_api_campaigns(tmp_path: Path) -> None:
    client, _ = _test_app(tmp_path)
    resp = client.get("/api/campaigns")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "campaigns" in data
    assert isinstance(data["campaigns"], list)
    assert "count" in data
    assert data["count"] == len(data["campaigns"])
    if data["campaigns"]:
        camp = data["campaigns"][0]
        assert "campaign_id" in camp
        assert "progress" in camp


# ---------------------------------------------------------------------------
# 4. POST /api/approve/{task_id} — writes decision, returns JSON
# ---------------------------------------------------------------------------


def test_post_approve_writes_decision(tmp_path: Path) -> None:
    import pradyos.sovereign_web as sw

    orig_dir = sw._DEFAULT_STATE_DIR
    orig_file = sw._DECISIONS_FILE

    sw._DEFAULT_STATE_DIR = tmp_path
    sw._DECISIONS_FILE = tmp_path / "sovereign_decisions.jsonl"

    try:
        bus = EventBus()
        app = create_app(bus=bus)
        client = TestClient(app)

        resp = client.post("/api/approve/task-xyz-123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["task_id"] == "task-xyz-123"
        assert data["decision"] == "approved"
        assert "ts" in data

        # Verify file was written
        decisions_path = tmp_path / "sovereign_decisions.jsonl"
        assert decisions_path.exists()
        line = json.loads(decisions_path.read_text().strip().split("\n")[0])
        assert line["task_id"] == "task-xyz-123"
        assert line["decision"] == "approved"
    finally:
        sw._DEFAULT_STATE_DIR = orig_dir
        sw._DECISIONS_FILE = orig_file


# ---------------------------------------------------------------------------
# 5. POST /api/reject/{task_id} — writes rejection decision
# ---------------------------------------------------------------------------


def test_post_reject_writes_decision(tmp_path: Path) -> None:
    import pradyos.sovereign_web as sw

    orig_dir = sw._DEFAULT_STATE_DIR
    orig_file = sw._DECISIONS_FILE

    sw._DEFAULT_STATE_DIR = tmp_path
    sw._DECISIONS_FILE = tmp_path / "sovereign_decisions.jsonl"

    try:
        bus = EventBus()
        app = create_app(bus=bus)
        client = TestClient(app)

        resp = client.post("/api/reject/task-abc-456")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["task_id"] == "task-abc-456"
        assert data["decision"] == "rejected"

        decisions_path = tmp_path / "sovereign_decisions.jsonl"
        line = json.loads(decisions_path.read_text().strip().split("\n")[0])
        assert line["decision"] == "rejected"
    finally:
        sw._DEFAULT_STATE_DIR = orig_dir
        sw._DECISIONS_FILE = orig_file


# ---------------------------------------------------------------------------
# 6. POST approve publishes bus event
# ---------------------------------------------------------------------------


def test_approve_publishes_bus_event(tmp_path: Path) -> None:
    import pradyos.sovereign_web as sw

    orig_dir = sw._DEFAULT_STATE_DIR
    orig_file = sw._DECISIONS_FILE

    sw._DEFAULT_STATE_DIR = tmp_path
    sw._DECISIONS_FILE = tmp_path / "sovereign_decisions.jsonl"

    try:
        bus = EventBus()
        events: list[dict] = []
        bus.subscribe("sovereign.approved", lambda t, p: events.append(p))

        app = create_app(bus=bus)
        client = TestClient(app)
        client.post("/api/approve/task-bus-test")
        assert any(e.get("task_id") == "task-bus-test" for e in events)
    finally:
        sw._DEFAULT_STATE_DIR = orig_dir
        sw._DECISIONS_FILE = orig_file


# ---------------------------------------------------------------------------
# 7. POST reject publishes bus event
# ---------------------------------------------------------------------------


def test_reject_publishes_bus_event(tmp_path: Path) -> None:
    import pradyos.sovereign_web as sw

    orig_dir = sw._DEFAULT_STATE_DIR
    orig_file = sw._DECISIONS_FILE

    sw._DEFAULT_STATE_DIR = tmp_path
    sw._DECISIONS_FILE = tmp_path / "sovereign_decisions.jsonl"

    try:
        bus = EventBus()
        events: list[dict] = []
        bus.subscribe("sovereign.rejected", lambda t, p: events.append(p))

        app = create_app(bus=bus)
        client = TestClient(app)
        client.post("/api/reject/task-rej-bus")
        assert any(e.get("task_id") == "task-rej-bus" for e in events)
    finally:
        sw._DEFAULT_STATE_DIR = orig_dir
        sw._DECISIONS_FILE = orig_file


# ---------------------------------------------------------------------------
# 8. GET /stream — SSE endpoint opens (200, text/event-stream)
# ---------------------------------------------------------------------------



def test_stream_endpoint_opens() -> None:
    """SSE endpoint must return 200 with text/event-stream content-type.

    The ASGI test transport awaits the full app coroutine, so any infinite
    generator blocks client.stream() before headers are delivered.  We
    monkey-patch sw._sse_generator with a finite stub for this test only;
    stream_events() resolves _sse_generator via LOAD_GLOBAL at call time, so
    the patch is transparent to the rest of the app.
    """
    import pradyos.sovereign_web as sw

    async def _finite_gen(queue: Any) -> Any:
        """Finite stand-in: yields the initial comment then terminates."""
        yield ": connected\n\n"

    original = sw._sse_generator
    sw._sse_generator = _finite_gen
    try:
        bus = EventBus()
        app = create_app(bus=bus)

        with TestClient(app, raise_server_exceptions=False) as client:
            with client.stream("GET", "/stream") as resp:
                assert resp.status_code == 200
                assert "text/event-stream" in resp.headers.get("content-type", "")
                lines = list(resp.iter_lines())

        assert any("connected" in ln for ln in lines if ln), (
            f"Expected ':connected' SSE comment in lines, got {lines}"
        )
    finally:
        sw._sse_generator = original


# ---------------------------------------------------------------------------
# 9. GET /api/status — no registry returns empty active_campaigns
# ---------------------------------------------------------------------------


def test_status_no_registry() -> None:
    app = create_app()  # no registry injected
    client = TestClient(app)
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["active_campaigns"] == []


# ---------------------------------------------------------------------------
# 10. GET /api/campaigns — no registry returns empty list
# ---------------------------------------------------------------------------


def test_campaigns_no_registry() -> None:
    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/campaigns")
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaigns"] == []
    assert data["count"] == 0
