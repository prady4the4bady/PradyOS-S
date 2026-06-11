"""Phase 28D: Decision Journal web endpoint tests (10 tests)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.decision_journal import DecisionJournal
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def journal() -> DecisionJournal:
    return DecisionJournal()


@pytest.fixture
def client_with_journal(journal: DecisionJournal) -> TestClient:
    return TestClient(create_app(decision_journal=journal))


@pytest.fixture
def client_no_journal() -> TestClient:
    return TestClient(create_app())


def _post_entry(client: TestClient, agent: str = "agent-x", dtype: str = "deploy") -> dict:
    resp = client.post("/api/v1/decisions", json={
        "agent_id": agent,
        "decision_type": dtype,
        "rationale": "test rationale",
        "outcome": "success",
    })
    return resp


# ---------------------------------------------------------------------------
# 1. POST /api/v1/decisions returns 200
# ---------------------------------------------------------------------------
def test_post_decisions_200(client_with_journal: TestClient) -> None:
    resp = _post_entry(client_with_journal)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. POST response has all DecisionEntry fields
# ---------------------------------------------------------------------------
def test_post_decisions_fields(client_with_journal: TestClient) -> None:
    resp = _post_entry(client_with_journal)
    data = resp.json()
    required = {
        "entry_id", "agent_id", "decision_type", "rationale",
        "outcome", "timestamp", "prev_hash", "content_hash",
    }
    assert required <= set(data.keys())


# ---------------------------------------------------------------------------
# 3. GET /api/v1/decisions returns 200
# ---------------------------------------------------------------------------
def test_get_decisions_200(client_with_journal: TestClient) -> None:
    resp = client_with_journal.get("/api/v1/decisions")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. GET response has entries, count, total keys
# ---------------------------------------------------------------------------
def test_get_decisions_keys(client_with_journal: TestClient) -> None:
    resp = client_with_journal.get("/api/v1/decisions")
    data = resp.json()
    assert "entries" in data
    assert "count" in data
    assert "total" in data


# ---------------------------------------------------------------------------
# 5. No journal → GET returns entries=[]
# ---------------------------------------------------------------------------
def test_get_no_journal(client_no_journal: TestClient) -> None:
    resp = client_no_journal.get("/api/v1/decisions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == []
    assert data["count"] == 0


# ---------------------------------------------------------------------------
# 6. No journal → POST returns error key
# ---------------------------------------------------------------------------
def test_post_no_journal(client_no_journal: TestClient) -> None:
    resp = _post_entry(client_no_journal)
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data


# ---------------------------------------------------------------------------
# 7. POST then GET reflects new entry
# ---------------------------------------------------------------------------
def test_post_then_get(client_with_journal: TestClient) -> None:
    post_resp = _post_entry(client_with_journal)
    entry_id = post_resp.json()["entry_id"]

    get_resp = client_with_journal.get("/api/v1/decisions")
    data = get_resp.json()
    ids = [e["entry_id"] for e in data["entries"]]
    assert entry_id in ids


# ---------------------------------------------------------------------------
# 8. GET ?limit=1 returns at most 1 entry
# ---------------------------------------------------------------------------
def test_get_limit(client_with_journal: TestClient) -> None:
    for _ in range(5):
        _post_entry(client_with_journal)
    resp = client_with_journal.get("/api/v1/decisions?limit=1")
    data = resp.json()
    assert len(data["entries"]) <= 1


# ---------------------------------------------------------------------------
# 9. GET ?agent_id=x filters correctly
# ---------------------------------------------------------------------------
def test_get_filter_agent(client_with_journal: TestClient) -> None:
    _post_entry(client_with_journal, agent="alpha")
    _post_entry(client_with_journal, agent="beta")
    _post_entry(client_with_journal, agent="alpha")

    resp = client_with_journal.get("/api/v1/decisions?agent_id=alpha")
    data = resp.json()
    assert len(data["entries"]) == 2
    assert all(e["agent_id"] == "alpha" for e in data["entries"])


# ---------------------------------------------------------------------------
# 10. verify_chain passes after multiple POST entries
# ---------------------------------------------------------------------------
def test_verify_chain_after_posts(
    client_with_journal: TestClient,
    journal: DecisionJournal,
) -> None:
    for _ in range(5):
        _post_entry(client_with_journal)
    assert journal.verify_chain() is True
