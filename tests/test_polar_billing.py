"""Polar.sh billing tests — checkout URL generation, configuration detection."""

from __future__ import annotations

import os

from pradyos.licensing import polar_billing


def test_checkout_url_returns_none_when_no_product_id():
    # Ensure env overrides are absent for this test
    for key in ("PRADYOS_POLAR_PRODUCT_PRO",):
        os.environ.pop(key, None)
    polar_billing.POLAR_PRODUCT_IDS["pro"] = ""
    assert polar_billing.checkout_url("pro") is None


def test_checkout_url_returns_url_when_product_id_set():
    polar_billing.POLAR_PRODUCT_IDS["sovereign"] = "abc123"
    url = polar_billing.checkout_url("sovereign")
    assert url == "https://buy.polar.sh/abc123"
    assert url is not None


def test_checkout_url_case_insensitive():
    polar_billing.POLAR_PRODUCT_IDS["enterprise"] = "ent-456"
    assert polar_billing.checkout_url("ENTERPRISE") == "https://buy.polar.sh/ent-456"


def test_is_configured_returns_false_when_no_token():
    os.environ.pop("POLAR_ACCESS_TOKEN", None)
    assert polar_billing.is_configured() is False


def test_is_configured_returns_true_when_token_set():
    os.environ["POLAR_ACCESS_TOKEN"] = "test-token"
    assert polar_billing.is_configured() is True
    del os.environ["POLAR_ACCESS_TOKEN"]


def test_checkout_url_unknown_tier():
    assert polar_billing.checkout_url("nonexistent") is None


def test_tier_from_webhook_stub():
    """Polar webhook verification is not yet implemented."""
    assert polar_billing.tier_from_webhook(b"{}", "") is None


def test_polar_error_derives_from_runtime_error():
    from pradyos.licensing.polar_billing import PolarError
    assert issubclass(PolarError, RuntimeError)
