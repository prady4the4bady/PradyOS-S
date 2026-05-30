"""Phase 91 — Sovereign GK Quantile Sketch HTTP routes.

Exposes a :class:`~pradyos.core.gk_quantile.GKSummary` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_gk_quantile_routes`, called *inside* the factory — the summary
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Where Phase 79's T-Digest is a centroid-based quantile estimator, this is the
rank-error-guaranteed Greenwald–Khanna sketch (true rank within ``±εn``).

Routes (mounted under ``/api/v1/quantile``):
  POST /api/v1/quantile/insert  body ``{"value": x}`` or ``{"values": [...]}``
  GET  /api/v1/quantile/query   ``?phi=0.95`` — the φ-quantile (422 if empty / φ∉[0,1])
  GET  /api/v1/quantile/count   ``{"count": n}``
  GET  /api/v1/quantile/stats   ``{epsilon, n, summary_size, capacity}``
  POST /api/v1/quantile/reset   body ``{"epsilon"?: float, "seed"?: int}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.gk_quantile import GKError, GKSummary

DEFAULT_EPSILON = 0.01


def register_gk_quantile_routes(app: Any, gk: Any | None = None) -> Any:
    """Register the /api/v1/quantile routes on ``app``; return the summary used.

    ``gk`` defaults to a fresh :class:`GKSummary` owned by this app instance
    (factory scope — never a module-level global)."""
    if gk is None:
        gk = GKSummary(DEFAULT_EPSILON)

    @app.post("/api/v1/quantile/insert")
    async def api_quantile_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "value or values is required"}, status_code=422)
        try:
            if "values" in body:
                values = body.get("values")
                if not isinstance(values, list):
                    return JSONResponse({"error": "values must be a list"}, status_code=422)
                added = gk.insert_many(values)
            elif "value" in body:
                gk.insert(body.get("value"))
                added = 1
            else:
                return JSONResponse({"error": "value or values is required"}, status_code=422)
        except GKError:
            return JSONResponse({"error": "value must be a number"}, status_code=422)
        return JSONResponse({"inserted": added, "n": gk.count()})

    @app.get("/api/v1/quantile/query")
    async def api_quantile_query(phi: float = Query(ge=0.0, le=1.0)) -> JSONResponse:
        value = gk.query(phi)
        if value is None:
            return JSONResponse({"error": "summary is empty"}, status_code=422)
        return JSONResponse({"phi": phi, "quantile": value, "n": gk.count()})

    @app.get("/api/v1/quantile/count")
    async def api_quantile_count() -> JSONResponse:
        return JSONResponse({"count": gk.count()})

    @app.get("/api/v1/quantile/stats")
    async def api_quantile_stats() -> JSONResponse:
        return JSONResponse(gk.stats())

    @app.post("/api/v1/quantile/reset")
    async def api_quantile_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            gk.reset(body.get("epsilon"), body.get("seed"))
        except GKError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(gk.stats())

    return gk
