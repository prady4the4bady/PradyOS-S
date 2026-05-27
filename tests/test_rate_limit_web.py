"""Phase 23D — FastAPI web tests for /api/v1/ratelimit/* (10 tests)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app
from pradyos.core.rate_limiter import RateLimiter


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def client_with_limiter():
    """TestClient backed by a real RateLimiter instance."""
    rl = RateLimiter(default_limit=5, default_window=60.0)
    app = create_app(rate_limiter=rl)
    return TestClient(app), rl


@pytest.fixture()
def client_no_limiter():
    """TestClient with NO rate_limiter (tests stub behaviour)."""
    app = create_app()
    return TestClient(app)


# ── 1. GET /api/v1/ratelimit/status returns 200 ───────────────────────────────

def test_status_returns_200(client_with_limiter):
    client, _ = client_with_limiter
    r = client.get("/api/v1/ratelimit/status")
    assert r.status_code == 200


# ── 2. status response has required keys ─────────────────────────────────────

def test_status_has_required_keys(client_with_limiter):
    client, _ = client_with_limiter
    data = client.get("/api/v1/ratelimit/status").json()
    for key in ("active_clients", "total_hits", "rules", "default_limit", "default_window"):
        assert key in data


# ── 3. POST /api/v1/ratelimit/rules returns 200 ───────────────────────────────

def test_set_rules_returns_200(client_with_limiter):
    client, _ = client_with_limiter
    r = client.post(
        "/api/v1/ratelimit/rules",
        json={"endpoint": "/api/test", "limit": 10, "window": 30.0},
    )
    assert r.status_code == 200


# ── 4. POST /api/v1/ratelimit/rules response has "set" key ───────────────────

def test_set_rules_has_set_key(client_with_limiter):
    client, _ = client_with_limiter
    data = client.post(
        "/api/v1/ratelimit/rules",
        json={"endpoint": "/api/test", "limit": 10, "window": 30.0},
    ).json()
    assert "set" in data


# ── 5. POST /api/v1/ratelimit/check returns 200 ───────────────────────────────

def test_check_returns_200(client_with_limiter):
    client, _ = client_with_limiter
    r = client.post(
        "/api/v1/ratelimit/check",
        json={"client_id": "user1", "endpoint": "/api/foo"},
    )
    assert r.status_code == 200


# ── 6. check response has "allowed" key ──────────────────────────────────────

def test_check_has_allowed_key(client_with_limiter):
    client, _ = client_with_limiter
    data = client.post(
        "/api/v1/ratelimit/check",
        json={"client_id": "user1", "endpoint": "/api/foo"},
    ).json()
    assert "allowed" in data


# ── 7. check allowed=True when under limit ───────────────────────────────────

def test_check_allowed_when_under_limit(client_with_limiter):
    client, _ = client_with_limiter
    data = client.post(
        "/api/v1/ratelimit/check",
        json={"client_id": "newuser", "endpoint": "/api/fresh"},
    ).json()
    assert data["allowed"] is True


# ── 8. No rate_limiter → GET status returns stub (active_clients=0) ──────────

def test_status_stub_when_no_limiter(client_no_limiter):
    data = client_no_limiter.get("/api/v1/ratelimit/status").json()
    assert data["active_clients"] == 0
    assert data["total_hits"] == 0
    assert data["rules"] == {}


# ── 9. No rate_limiter → POST check returns allowed=True ─────────────────────

def test_check_stub_allowed_when_no_limiter(client_no_limiter):
    data = client_no_limiter.post(
        "/api/v1/ratelimit/check",
        json={"client_id": "anyone", "endpoint": "/any"},
    ).json()
    assert data["allowed"] is True


# ── 10. POST rules then check enforces new rule ───────────────────────────────

def test_post_rules_then_check_enforces_rule(client_with_limiter):
    client, _ = client_with_limiter
    # Set a very tight rule: limit=1 on /api/strict
    client.post(
        "/api/v1/ratelimit/rules",
        json={"endpoint": "/api/strict", "limit": 1, "window": 60.0},
    )
    # First check should be allowed
    r1 = client.post(
        "/api/v1/ratelimit/check",
        json={"client_id": "u1", "endpoint": "/api/strict"},
    ).json()
    assert r1["allowed"] is True
    # Second check should be denied
    r2 = client.post(
        "/api/v1/ratelimit/check",
        json={"client_id": "u1", "endpoint": "/api/strict"},
    ).json()
    assert r2["allowed"] is False
