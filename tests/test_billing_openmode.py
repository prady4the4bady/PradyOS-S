"""Tests for monetization: lowered $5–$50 prices, the open-mode master switch,
the Stripe billing seam, and webhook tier activation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pradyos.licensing import stripe_billing
from pradyos.licensing.vault import LicenseVault
from pradyos.sovereign_web import create_app


def _client() -> TestClient:
    return TestClient(create_app())


# ── lowered prices ($5–$50) ─────────────────────────────────────────────────


def test_prices_in_5_to_50_band():
    prices = {p["tier"]: p["price"] for p in LicenseVault.pricing()}
    assert prices == {"free": 0, "pro": 5, "sovereign": 25, "enterprise": 50}


def test_stripe_price_ids_present_for_paid_tiers():
    assert stripe_billing.price_id_for("pro").startswith("price_")
    assert stripe_billing.price_id_for("sovereign").startswith("price_")
    assert stripe_billing.price_id_for("enterprise").startswith("price_")
    assert stripe_billing.price_id_for("free") is None


def test_stripe_price_env_override(monkeypatch):
    monkeypatch.setenv("PRADYOS_STRIPE_PRICE_PRO", "price_override123")
    assert stripe_billing.price_id_for("pro") == "price_override123"


# ── open mode (master switch) ───────────────────────────────────────────────


def test_open_mode_unlocks_everything():
    v = LicenseVault()
    assert v.entitled("cloud_ai") is False  # gated on free tier
    v.set_open_mode(True)
    assert v.entitled("cloud_ai") is True
    assert v.entitled("enterprise_seats") is True
    v.set_open_mode(False)
    assert v.entitled("cloud_ai") is False


def test_open_mode_from_env(monkeypatch):
    monkeypatch.setenv("PRADYOS_OPEN_MODE", "true")
    v = LicenseVault()
    assert v.open_mode() is True
    assert v.status()["open_mode"] is True


def test_open_mode_endpoint_toggles():
    c = _client()
    assert c.get("/api/v1/license/open-mode").json()["open_mode"] is False
    r = c.post("/api/v1/license/open-mode", json={"enabled": True})
    assert r.status_code == 200 and r.json()["open_mode"] is True
    assert c.get("/api/v1/license/entitled?feature=sovereign_mode").json()["entitled"] is True
    c.post("/api/v1/license/open-mode", json={"enabled": False})


def test_open_mode_requires_enabled_field():
    assert _client().post("/api/v1/license/open-mode", json={}).status_code == 422


def test_open_mode_admin_token_guard(monkeypatch):
    monkeypatch.setenv("PRADYOS_ADMIN_TOKEN", "s3cret")
    c = _client()
    assert c.post("/api/v1/license/open-mode", json={"enabled": True}).status_code == 403
    ok = c.post("/api/v1/license/open-mode", json={"enabled": True}, headers={"X-Admin-Token": "s3cret"})
    assert ok.status_code == 200


# ── checkout seam + webhook ─────────────────────────────────────────────────


def test_checkout_pending_without_stripe(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("PRADYOS_BILLING_CHECKOUT_URL", raising=False)
    body = _client().post("/api/v1/billing/checkout", json={"tier": "pro"}).json()
    assert body["status"] == "pending"
    assert body["price"] == 5


def test_checkout_open_mode_short_circuits():
    c = _client()
    c.post("/api/v1/license/open-mode", json={"enabled": True})
    body = c.post("/api/v1/billing/checkout", json={"tier": "sovereign"}).json()
    assert body["status"] == "open_mode"
    c.post("/api/v1/license/open-mode", json={"enabled": False})


def test_webhook_rejects_unsigned():
    assert _client().post("/api/v1/billing/webhook", content=b"{}").status_code == 400


def test_grant_tier_activates_without_signature():
    v = LicenseVault()
    v.grant_tier("sovereign", holder="stripe-subscriber")
    assert v.tier() == "sovereign"
    assert v.entitled("cloud_ai") is True


def test_stripe_not_configured_by_default(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert stripe_billing.is_configured() is False
