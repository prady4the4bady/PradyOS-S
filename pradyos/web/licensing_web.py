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
from pradyos.licensing.vault import PRICING
from pradyos.web._responses import read_json as _json


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
        """Open a checkout for a tier. Honest stub: returns a hosted-checkout URL
        only if ``PRADYOS_BILLING_CHECKOUT_URL`` is configured, else 'pending'."""
        body = await _json(request)
        tier = str((body or {}).get("tier", "")).lower() if isinstance(body, dict) else ""
        if tier not in PRICING:
            return JSONResponse({"error": f"unknown tier {tier!r}"}, status_code=422)
        if tier == "free":
            return JSONResponse({"tier": tier, "status": "active", "checkout_url": None})
        base = os.environ.get("PRADYOS_BILLING_CHECKOUT_URL")
        if base:
            sep = "&" if "?" in base else "?"
            return JSONResponse(
                {
                    "tier": tier,
                    "status": "redirect",
                    "checkout_url": f"{base}{sep}tier={tier}",
                    "price": PRICING[tier]["price_year"],
                }
            )
        return JSONResponse(
            {
                "tier": tier,
                "status": "pending",
                "checkout_url": None,
                "price": PRICING[tier]["price_year"],
                "message": (
                    "No payment processor configured. Set PRADYOS_BILLING_CHECKOUT_URL, "
                    "or install a signed license key offline to activate this tier."
                ),
            }
        )

    return lic
