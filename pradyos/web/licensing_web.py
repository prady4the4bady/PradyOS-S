"""HTTP surface for LICENSING — signed offline licenses + entitlements.

Registers ``/api/v1/license/*``: inspect the active tier + entitlements, install
a signed license token, check a single feature, and list the tier catalogue.
Factory-scoped, deterministic, fully offline.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.licensing import LicenseError, LicenseVault
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

    return lic
