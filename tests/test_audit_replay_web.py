"""Phase 25 — /api/v1/audit/replay web endpoint tests (10 tests)."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from pradyos.core.audit_replay import AuditReplayEngine
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_no_engine() -> TestClient:
    """App with no replay_engine attached."""
    app = create_app()
    return TestClient(app)


@pytest.fixture()
def engine_with_entries() -> AuditReplayEngine:
    engine = AuditReplayEngine()
    now = time.time()
    engine.add_entry("boot", {"phase": "25"}, timestamp=now - 10)
    engine.add_entry("ready", {"status": "ok"}, timestamp=now - 5)
    engine.add_entry("future", {"x": 1}, timestamp=now + 1000)
    return engine


@pytest.fixture()
def client_with_engine(engine_with_entries: AuditReplayEngine) -> TestClient:
    app = create_app(replay_engine=engine_with_entries)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. GET /api/v1/audit/replay returns 200
# ---------------------------------------------------------------------------

def test_replay_returns_200(client_no_engine: TestClient) -> None:
    resp = client_no_engine.get("/api/v1/audit/replay")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Response has keys: at, entries, state, event_count
# ---------------------------------------------------------------------------

def test_replay_response_has_required_keys(client_no_engine: TestClient) -> None:
    resp = client_no_engine.get("/api/v1/audit/replay")
    data = resp.json()
    assert "at" in data
    assert "entries" in data
    assert "state" in data
    assert "event_count" in data


# ---------------------------------------------------------------------------
# 3. No replay_engine → returns event_count=0
# ---------------------------------------------------------------------------

def test_no_engine_returns_event_count_zero(client_no_engine: TestClient) -> None:
    resp = client_no_engine.get("/api/v1/audit/replay")
    assert resp.json()["event_count"] == 0


# ---------------------------------------------------------------------------
# 4. No replay_engine → returns empty entries list
# ---------------------------------------------------------------------------

def test_no_engine_returns_empty_entries(client_no_engine: TestClient) -> None:
    resp = client_no_engine.get("/api/v1/audit/replay")
    assert resp.json()["entries"] == []


# ---------------------------------------------------------------------------
# 5. With replay_engine → event_count matches added entries
# ---------------------------------------------------------------------------

def test_with_engine_event_count_matches(client_with_engine: TestClient) -> None:
    # engine has 2 past entries + 1 future entry; default at=now should include 2
    resp = client_with_engine.get("/api/v1/audit/replay")
    data = resp.json()
    # event_count should be 2 (past entries only, default at≈now)
    assert data["event_count"] == 2


# ---------------------------------------------------------------------------
# 6. GET with ?at=<past_ts> filters entries correctly
# ---------------------------------------------------------------------------

def test_past_timestamp_filters_entries(client_with_engine: TestClient) -> None:
    # Use a timestamp before all entries
    past_ts = time.time() - 1000
    resp = client_with_engine.get(f"/api/v1/audit/replay?at={past_ts}")
    assert resp.json()["event_count"] == 0


# ---------------------------------------------------------------------------
# 7. GET with ?at=<future_ts> includes all entries
# ---------------------------------------------------------------------------

def test_future_timestamp_includes_all_entries(client_with_engine: TestClient) -> None:
    future_ts = time.time() + 9999
    resp = client_with_engine.get(f"/api/v1/audit/replay?at={future_ts}")
    # engine has 3 entries total (2 past + 1 future)
    assert resp.json()["event_count"] == 3


# ---------------------------------------------------------------------------
# 8. entries in response are list type
# ---------------------------------------------------------------------------

def test_entries_is_list(client_with_engine: TestClient) -> None:
    resp = client_with_engine.get("/api/v1/audit/replay")
    assert isinstance(resp.json()["entries"], list)


# ---------------------------------------------------------------------------
# 9. state in response is dict type
# ---------------------------------------------------------------------------

def test_state_is_dict(client_with_engine: TestClient) -> None:
    resp = client_with_engine.get("/api/v1/audit/replay")
    assert isinstance(resp.json()["state"], dict)


# ---------------------------------------------------------------------------
# 10. at in response is float
# ---------------------------------------------------------------------------

def test_at_is_float(client_with_engine: TestClient) -> None:
    resp = client_with_engine.get("/api/v1/audit/replay")
    assert isinstance(resp.json()["at"], float)
