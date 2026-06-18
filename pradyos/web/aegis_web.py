"""HTTP surface for AEGIS — software integrity & tamper-evidence.

Registers ``/api/v1/aegis/*``: verify the running tree against the signed manifest
and report status. Read-only; manifest *building/signing* is a vendor-side offline
step (``scripts/build_manifest.py``), never exposed over HTTP.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.aegis import IntegrityGuard


def register_aegis_routes(app: Any, guard: Any | None = None) -> Any:
    """Register the ``/api/v1/aegis`` routes on ``app``; return the guard."""
    g: IntegrityGuard = guard if guard is not None else IntegrityGuard()

    def _entitlement_error() -> JSONResponse:
        vault = getattr(app.state, "license_vault", None)
        current = vault.tier() if vault else "free"
        return JSONResponse(
            {"error": "tier_required", "feature": "aegis_integrity",
             "required": "enterprise", "current": current,
             "upgrade_url": "/billing"},
            status_code=402,
        )

    @app.get("/api/v1/aegis/verify")
    async def api_aegis_verify(request: Request) -> JSONResponse:
        vault = getattr(app.state, "license_vault", None)
        if vault and not vault.entitled("aegis_integrity"):
            return _entitlement_error()
        return JSONResponse(g.verify())

    @app.get("/api/v1/aegis/status")
    async def api_aegis_status(request: Request) -> JSONResponse:
        vault = getattr(app.state, "license_vault", None)
        if vault and not vault.entitled("aegis_integrity"):
            return _entitlement_error()
        return JSONResponse(g.status())

    return g
