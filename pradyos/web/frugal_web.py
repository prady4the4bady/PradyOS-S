"""Phase 125 — Sovereign Frugal Streaming quantile HTTP routes.

Exposes a :class:`~pradyos.core.frugal.FrugalQuantile` over REST. Routes are registered
onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_frugal_routes`, called *inside* the factory — the (single-value) estimator
lives in factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

Routes (mounted under ``/api/v1/frugal``):
  POST   /api/v1/frugal/add       body ``{"value": number}`` — fold a stream value
  GET    /api/v1/frugal/estimate  ``{estimate, quantile, count}``
  GET    /api/v1/frugal/stats     ``{quantile, estimate, step, count, seed}``
  DELETE /api/v1/frugal/reset     body ``{"quantile"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.frugal import FrugalQuantile, FrugalError


def register_frugal_routes(app: Any, frugal: Any | None = None) -> Any:
    """Register the /api/v1/frugal routes on ``app``; return the estimator used.

    ``frugal`` defaults to a fresh :class:`FrugalQuantile` owned by this app instance
    (factory scope — never a module-level global)."""
    if frugal is None:
        frugal = FrugalQuantile()

    @app.post("/api/v1/frugal/add")
    async def api_frugal_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            frugal.add(body["value"])
        except FrugalError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "estimate": frugal.estimate(),
                            "count": frugal.count})

    @app.get("/api/v1/frugal/estimate")
    async def api_frugal_estimate() -> JSONResponse:
        return JSONResponse({"estimate": frugal.estimate(), "quantile": frugal.quantile,
                            "count": frugal.count})

    @app.get("/api/v1/frugal/stats")
    async def api_frugal_stats() -> JSONResponse:
        return JSONResponse(frugal.stats())

    @app.delete("/api/v1/frugal/reset")
    async def api_frugal_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            frugal.reset(body.get("quantile"), body.get("seed"))
        except FrugalError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(frugal.stats())

    return frugal
