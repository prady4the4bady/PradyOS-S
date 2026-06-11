"""Phase 95 — Sovereign Lossy Counting HTTP routes.

Exposes a :class:`~pradyos.core.lossy_count.LossyCount` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_lossy_count_routes`, called *inside* the factory — the counter
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Like Phases 76/94 this estimates frequencies, but **deterministically** (no
hashing) with a hard ε-error guarantee — and it is **append-only** (a negative
``count`` is rejected). Elements are normalised to strings for transport.

Routes (mounted under ``/api/v1/lossycount``):
  POST /api/v1/lossycount/update         ``?count=N`` body ``{"element": x}`` / ``{"elements": [...]}``
  GET  /api/v1/lossycount/estimate       ``?element=x`` — tracked frequency (0 if absent)
  GET  /api/v1/lossycount/heavy_hitters   ``?support=0.05`` — items with freq ≥ (support−ε)·n
  GET  /api/v1/lossycount/stats          ``{epsilon, n, bucket_width, entries, current_bucket}``
  POST /api/v1/lossycount/reset          body ``{"epsilon"?: float}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.lossy_count import LossyCount, LossyCountError

DEFAULT_EPSILON = 0.001


def register_lossy_count_routes(app: Any, lossy: Any | None = None) -> Any:
    """Register the /api/v1/lossycount routes on ``app``; return the counter used.

    ``lossy`` defaults to a fresh :class:`LossyCount` owned by this app instance
    (factory scope — never a module-level global)."""
    if lossy is None:
        lossy = LossyCount(DEFAULT_EPSILON)

    @app.post("/api/v1/lossycount/update")
    async def api_lossy_update(request: Request, count: int = Query(default=1)) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "element or elements is required"}, status_code=422)
        try:
            if "elements" in body:
                elements = body.get("elements")
                if not isinstance(elements, list):
                    return JSONResponse({"error": "elements must be a list"}, status_code=422)
                for element in elements:
                    lossy.update(str(element), count)
                updated = len(elements)
            elif "element" in body:
                lossy.update(str(body.get("element")), count)
                updated = 1
            else:
                return JSONResponse({"error": "element or elements is required"}, status_code=422)
        except LossyCountError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"updated": updated, "n": lossy.n})

    @app.get("/api/v1/lossycount/estimate")
    async def api_lossy_estimate(element: str) -> JSONResponse:
        return JSONResponse({"element": element, "estimate": lossy.estimate(element)})

    @app.get("/api/v1/lossycount/heavy_hitters")
    async def api_lossy_heavy_hitters(support: float = Query(gt=0.0, le=1.0)) -> JSONResponse:
        return JSONResponse({"support": support, "heavy_hitters": lossy.heavy_hitters(support)})

    @app.get("/api/v1/lossycount/stats")
    async def api_lossy_stats() -> JSONResponse:
        return JSONResponse(lossy.stats())

    @app.post("/api/v1/lossycount/reset")
    async def api_lossy_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            lossy.reset(body.get("epsilon"), body.get("seed"))
        except LossyCountError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(lossy.stats())

    return lossy
