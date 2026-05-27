"""Phase 29D: Capability Registry web endpoint tests (10 tests)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.capability_registry import CapabilityRegistry
from pradyos.sovereign_web import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry() -> CapabilityRegistry:
    return CapabilityRegistry()


@pytest.fixture
def client_with_registry(registry: CapabilityRegistry) -> TestClient:
    return TestClient(create_app(capability_registry=registry))


@pytest.fixture
def client_no_registry() -> TestClient:
    return TestClient(create_app())


def _post_capability(client: TestClient, name: str = "mod-alpha", version: str = "1.0") -> dict:
    return client.post("/api/v1/capabilities", json={
        "name": name,
        "version": version,
        "provided_apis": [f"/api/{name}"],
        "consumed_apis": [],
        "status": "active",
        "metadata": {"owner": "test"},
    })


# ---------------------------------------------------------------------------
# 1. GET /api/v1/capabilities returns 200
# ---------------------------------------------------------------------------
def test_get_capabilities_200(client_with_registry: TestClient) -> None:
    resp = client_with_registry.get("/api/v1/capabilities")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Response has "capabilities" and "summary" keys
# ---------------------------------------------------------------------------
def test_get_capabilities_keys(client_with_registry: TestClient) -> None:
    resp = client_with_registry.get("/api/v1/capabilities")
    data = resp.json()
    assert "capabilities" in data
    assert "summary" in data


# ---------------------------------------------------------------------------
# 3. No registry → capabilities is []
# ---------------------------------------------------------------------------
def test_get_no_registry_empty(client_no_registry: TestClient) -> None:
    resp = client_no_registry.get("/api/v1/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capabilities"] == []


# ---------------------------------------------------------------------------
# 4. POST /api/v1/capabilities returns 200
# ---------------------------------------------------------------------------
def test_post_capabilities_200(client_with_registry: TestClient) -> None:
    resp = _post_capability(client_with_registry)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. POST response has all Capability fields
# ---------------------------------------------------------------------------
def test_post_capabilities_fields(client_with_registry: TestClient) -> None:
    resp = _post_capability(client_with_registry)
    data = resp.json()
    required = {
        "name", "version", "provided_apis", "consumed_apis",
        "status", "registered_at", "metadata",
    }
    assert required <= set(data.keys())


# ---------------------------------------------------------------------------
# 6. No registry → POST returns error key
# ---------------------------------------------------------------------------
def test_post_no_registry_error(client_no_registry: TestClient) -> None:
    resp = _post_capability(client_no_registry)
    assert resp.status_code == 200
    assert "error" in resp.json()


# ---------------------------------------------------------------------------
# 7. POST then GET reflects new capability
# ---------------------------------------------------------------------------
def test_post_then_get_reflects(client_with_registry: TestClient) -> None:
    _post_capability(client_with_registry, name="mod-beta", version="2.0")
    resp = client_with_registry.get("/api/v1/capabilities")
    names = [c["name"] for c in resp.json()["capabilities"]]
    assert "mod-beta" in names


# ---------------------------------------------------------------------------
# 8. GET /api/v1/capabilities/{name} returns 200 for known name
# ---------------------------------------------------------------------------
def test_get_capability_by_name_200(client_with_registry: TestClient) -> None:
    _post_capability(client_with_registry, name="mod-gamma")
    resp = client_with_registry.get("/api/v1/capabilities/mod-gamma")
    assert resp.status_code == 200
    assert resp.json()["name"] == "mod-gamma"


# ---------------------------------------------------------------------------
# 9. GET /api/v1/capabilities/{unknown} returns 404
# ---------------------------------------------------------------------------
def test_get_capability_unknown_404(client_with_registry: TestClient) -> None:
    resp = client_with_registry.get("/api/v1/capabilities/does-not-exist")
    assert resp.status_code == 404
    assert "error" in resp.json()


# ---------------------------------------------------------------------------
# 10. summary active count updates after POST
# ---------------------------------------------------------------------------
def test_summary_active_count_updates(client_with_registry: TestClient) -> None:
    before = client_with_registry.get("/api/v1/capabilities").json()["summary"].get("active", 0)
    _post_capability(client_with_registry, name="mod-delta", version="1.0")
    after = client_with_registry.get("/api/v1/capabilities").json()["summary"]["active"]
    assert after == before + 1
