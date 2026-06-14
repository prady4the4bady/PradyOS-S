"""Tests for the rebuilt console + monetization seam + NIM model aliases.

Covers the new surfaces added alongside the Sovereign Command Console:
  * the price book (``LicenseVault.pricing``) and its HTTP endpoint,
  * the honest checkout stub (pending by default, redirect when configured),
  * NIM model-alias resolution (``minimax`` → MiniMax-M3) and the optional
    ``max_tokens`` / ``top_p`` generation controls reaching the request body,
  * the console HTML keeping the brand-presence marker and the four themes.
"""

from __future__ import annotations

import json
import urllib.request

from fastapi.testclient import TestClient

from pradyos.core.llm import OpenAICompatProvider, _resolve_model, resolve_provider
from pradyos.licensing.vault import LicenseVault
from pradyos.sovereign_web import create_app
from pradyos.web.console import CONSOLE_HTML


def _client() -> TestClient:
    return TestClient(create_app())


# ── price book ────────────────────────────────────────────────────────────────


def test_pricing_has_four_ordered_tiers():
    plans = LicenseVault.pricing()
    assert [p["tier"] for p in plans] == ["free", "pro", "sovereign", "enterprise"]


def test_pricing_in_5_to_50_band():
    prices = {p["tier"]: p["price"] for p in LicenseVault.pricing()}
    assert prices["free"] == 0
    assert prices["pro"] == 5
    assert prices["sovereign"] == 25
    assert prices["enterprise"] == 50


def test_pricing_sovereign_is_featured():
    feat = {p["tier"]: p["feat"] for p in LicenseVault.pricing()}
    assert feat["sovereign"] is True
    assert feat["free"] is False


def test_pricing_endpoint_returns_plans():
    resp = _client().get("/api/v1/license/pricing")
    assert resp.status_code == 200
    data = resp.json()
    assert data["currency"] == "USD"
    assert len(data["plans"]) == 4


# ── checkout stub ───────────────────────────────────────────────────────────────


def test_checkout_free_is_active_no_url():
    resp = _client().post("/api/v1/billing/checkout", json={"tier": "free"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["checkout_url"] is None


def test_checkout_paid_pending_without_processor(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("PRADYOS_BILLING_CHECKOUT_URL", raising=False)
    resp = _client().post("/api/v1/billing/checkout", json={"tier": "sovereign"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["price"] == 25
    assert body["checkout_url"] is None


def test_checkout_redirects_when_configured(monkeypatch):
    monkeypatch.setenv("PRADYOS_BILLING_CHECKOUT_URL", "https://pay.example/buy")
    resp = _client().post("/api/v1/billing/checkout", json={"tier": "pro"})
    body = resp.json()
    assert body["status"] == "redirect"
    assert body["checkout_url"] == "https://pay.example/buy?tier=pro"


def test_checkout_rejects_unknown_tier():
    resp = _client().post("/api/v1/billing/checkout", json={"tier": "platinum"})
    assert resp.status_code == 422


# ── NIM model aliases + generation controls ────────────────────────────────────


def test_resolve_model_aliases():
    assert _resolve_model("minimax") == "minimaxai/minimax-m3"
    assert _resolve_model("llama") == "meta/llama-3.3-70b-instruct"
    assert _resolve_model("nemotron").startswith("nvidia/")
    # unknown values pass through verbatim (treated as a full model id)
    assert _resolve_model("vendor/custom-9b") == "vendor/custom-9b"


def test_nim_provider_carries_generation_controls():
    p = resolve_provider(
        {
            "PRADYOS_LLM_PROVIDER": "nim",
            "PRADYOS_LLM_API_KEY": "secret",
            "PRADYOS_LLM_MODEL": "minimax",
            "PRADYOS_LLM_MAX_TOKENS": "8192",
            "PRADYOS_LLM_TOP_P": "0.95",
        }
    )
    assert isinstance(p, OpenAICompatProvider)
    assert p.model == "minimaxai/minimax-m3"
    assert p.max_tokens == 8192 and p.top_p == 0.95


def test_generation_controls_reach_request_body(monkeypatch):
    captured: dict[str, object] = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

    def _fake_urlopen(req, timeout=0):  # noqa: ARG001
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    p = OpenAICompatProvider(
        base_url="https://integrate.api.nvidia.com/v1",
        model="minimaxai/minimax-m3",
        api_key="k",
        max_tokens=8192,
        top_p=0.95,
    )
    assert p.generate("hi") == "ok"
    body = captured["body"]
    assert body["model"] == "minimaxai/minimax-m3"
    assert body["max_tokens"] == 8192
    assert body["top_p"] == 0.95


# ── console HTML invariants ────────────────────────────────────────────────────


def test_console_keeps_brand_marker():
    assert "PRADY OS" in CONSOLE_HTML


def test_console_defines_four_time_themes():
    for theme in ("dawn", "day", "dusk", "night"):
        assert f'data-theme="{theme}"' in CONSOLE_HTML


def test_console_served_at_root():
    resp = _client().get("/")
    assert resp.status_code == 200
    assert "PRADYOS" in resp.text
