"""HTTP surface for LICENSING — signed offline licenses + entitlements + pricing.

Registers ``/api/v1/license/*``: inspect the active tier + entitlements, install
a signed license token, check a single feature, list the tier catalogue, read the
public price book, and open a checkout. Factory-scoped, deterministic, offline.

The checkout endpoint is a thin, honest *seam*: by default it returns a
"provisioning" response (no payment processor wired), and if the Sovereign sets
``PRADYOS_BILLING_CHECKOUT_URL`` it hands back a hosted-checkout link with the
tier appended. A real Stripe/Paddle/LemonSqueezy session plugs in right here —
the rest of the OS already gates on the *signed license*, never on the payment.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.licensing import LicenseError, LicenseVault
from pradyos.licensing import stripe_billing
from pradyos.licensing.vault import PRICING
from pradyos.web._responses import read_json as _json


def _admin_ok(request: Request) -> bool:
    """Gate admin actions: allowed unless PRADYOS_ADMIN_TOKEN is set, in which
    case the X-Admin-Token header must match (local single-user OS → open)."""
    token = os.environ.get("PRADYOS_ADMIN_TOKEN")
    if not token:
        return True
    return request.headers.get("X-Admin-Token") == token


def register_license_routes(app: Any, vault: Any | None = None) -> Any:
    """Register the ``/api/v1/license`` routes on ``app``; return the vault used."""
    lic: LicenseVault = vault if vault is not None else LicenseVault()

    @app.get("/api/v1/license/status")
    async def api_license_status() -> JSONResponse:
        return JSONResponse(lic.status())

    @app.get("/api/v1/license/tiers")
    async def api_license_tiers() -> JSONResponse:
        return JSONResponse({"tiers": lic.tiers()})

    @app.get("/api/v1/license/entitled")
    async def api_license_entitled(feature: str = Query(...)) -> JSONResponse:
        return JSONResponse({"feature": feature, "entitled": lic.entitled(feature)})

    @app.post("/api/v1/license/install")
    async def api_license_install(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "token" not in body:
            return JSONResponse({"error": "token is required"}, status_code=422)
        try:
            return JSONResponse(lic.install(body["token"]))
        except LicenseError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.delete("/api/v1/license/reset")
    async def api_license_reset() -> JSONResponse:
        return JSONResponse(lic.clear())

    @app.get("/api/v1/license/pricing")
    async def api_license_pricing() -> JSONResponse:
        """Public price book (free→enterprise) for the upgrade modal."""
        return JSONResponse({"currency": "USD", "period": "year", "plans": lic.pricing()})

    @app.post("/api/v1/billing/checkout")
    async def api_billing_checkout(request: Request) -> JSONResponse:
        """Open a checkout for a tier. Uses Stripe Checkout when ``STRIPE_SECRET_KEY``
        is set; otherwise falls back to ``PRADYOS_BILLING_CHECKOUT_URL`` or a
        'pending' stub (install a signed key offline to activate)."""
        body = await _json(request)
        tier = str((body or {}).get("tier", "")).lower() if isinstance(body, dict) else ""
        if tier not in PRICING:
            return JSONResponse({"error": f"unknown tier {tier!r}"}, status_code=422)
        if tier == "free":
            return JSONResponse({"tier": tier, "status": "active", "checkout_url": None})
        if lic.open_mode():
            return JSONResponse(
                {"tier": tier, "status": "open_mode", "checkout_url": None,
                 "message": "Open mode is on — every feature is already free."}
            )
        # 1) real Stripe Checkout when configured
        if stripe_billing.is_configured():
            try:
                return JSONResponse(stripe_billing.create_checkout_session(tier))
            except stripe_billing.StripeError as exc:
                return JSONResponse({"tier": tier, "status": "error", "error": str(exc)}, status_code=502)
        # 2) generic hosted-checkout base URL
        base = os.environ.get("PRADYOS_BILLING_CHECKOUT_URL")
        if base:
            sep = "&" if "?" in base else "?"
            return JSONResponse(
                {"tier": tier, "status": "redirect",
                 "checkout_url": f"{base}{sep}tier={tier}", "price": PRICING[tier]["price_year"]}
            )
        # 3) honest pending stub
        return JSONResponse(
            {
                "tier": tier,
                "status": "pending",
                "checkout_url": None,
                "price": PRICING[tier]["price_year"],
                "message": (
                    "No payment processor configured. Set STRIPE_SECRET_KEY (+ price ids), "
                    "or install a signed license key offline to activate this tier."
                ),
            }
        )

    @app.post("/api/v1/billing/webhook")
    async def api_billing_webhook(request: Request) -> JSONResponse:
        """Stripe webhook: on a verified, completed checkout, activate the tier."""
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        try:
            tier = stripe_billing.tier_from_webhook(payload, sig)
        except stripe_billing.StripeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if tier:
            lic.grant_tier(tier, holder="stripe-subscriber")
            return JSONResponse({"activated": tier})
        return JSONResponse({"activated": None})

    @app.get("/api/v1/license/open-mode")
    async def api_open_mode_get() -> JSONResponse:
        return JSONResponse({"open_mode": lic.open_mode()})

    @app.post("/api/v1/license/open-mode")
    async def api_open_mode_set(request: Request) -> JSONResponse:
        """Sovereign master switch: flip all-features-free on/off."""
        if not _admin_ok(request):
            return JSONResponse({"error": "admin token required"}, status_code=403)
        body = await _json(request)
        if not isinstance(body, dict) or "enabled" not in body:
            return JSONResponse({"error": "enabled (bool) is required"}, status_code=422)
        return JSONResponse(lic.set_open_mode(bool(body["enabled"])))

    return lic
