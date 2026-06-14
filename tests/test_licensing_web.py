"""Tests for the /api/v1/license endpoints."""

from __future__ import annotations

import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pradyos.licensing import LicenseVault
from pradyos.web.licensing_web import register_license_routes


class _Ok:
    def verify(self, payload: bytes, signature: bytes) -> bool:
        return True


def _token(payload: dict) -> str:
    b = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{b}.c2ln"


@pytest.fixture()
def client():
    app = FastAPI()
    register_license_routes(app, LicenseVault(verifier=_Ok()))
    return TestClient(app)


def test_status_free_by_default(client):
    st = client.get("/api/v1/license/status").json()
    assert st["tier"] == "free" and st["entitlements"]["sovereign_mode"] is False


def test_tiers_catalogue(client):
    tiers = client.get("/api/v1/license/tiers").json()["tiers"]
    assert "sovereign_mode" in tiers["sovereign"]


def test_entitled_endpoint(client):
    assert (
        client.get("/api/v1/license/entitled", params={"feature": "manual_mode"}).json()["entitled"]
        is True
    )
    assert (
        client.get("/api/v1/license/entitled", params={"feature": "cloud_ai"}).json()["entitled"]
        is False
    )


def test_install_unlocks_then_reset(client):
    st = client.post(
        "/api/v1/license/install", json={"token": _token({"tier": "sovereign"})}
    ).json()
    assert st["tier"] == "sovereign" and st["entitlements"]["sovereign_mode"] is True
    assert client.delete("/api/v1/license/reset").json()["tier"] == "free"


def test_install_missing_token_422(client):
    assert client.post("/api/v1/license/install", json={}).status_code == 422


def test_install_bad_token_422(client):
    assert client.post("/api/v1/license/install", json={"token": "garbage"}).status_code == 422
