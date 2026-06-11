"""Phase 99 — Sovereign Misra-Gries HTTP routes.

Exposes a :class:`~pradyos.core.misra_gries.MisraGries` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_misra_gries_routes`, called *inside* the factory — the counter
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Like Phases 87/95 this finds heavy hitters deterministically, but via the original
Misra-Gries *decrement-all* rule (vs Space-Saving's evict-minimum and Lossy
Counting's window-sweep). Append-only: a non-positive ``count`` is rejected.
Elements are normalised to strings for transport.

Routes (mounted under ``/api/v1/misragries``):
  POST /api/v1/misragries/update         ``?count=N`` body ``{"element": x}`` / ``{"elements": [...]}``
  GET  /api/v1/misragries/estimate       ``?element=x`` — stored (under-)count (0 if absent)
  GET  /api/v1/misragries/heavy_hitters   ``?support=0.1`` — items with count ≥ (support−1/(k+1))·n
  GET  /api/v1/misragries/stats          ``{k, n, counters, threshold}``
  POST /api/v1/misragries/reset          body ``{"k"?: int}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.misra_gries import MisraGries, MisraGriesError

DEFAULT_K = 100


def register_misra_gries_routes(app: Any, misra: Any | None = None) -> Any:
    """Register the /api/v1/misragries routes on ``app``; return the counter used.

    ``misra`` defaults to a fresh :class:`MisraGries` owned by this app instance
    (factory scope — never a module-level global)."""
    if misra is None:
        misra = MisraGries(DEFAULT_K)

    @app.post("/api/v1/misragries/update")
    async def api_mg_update(request: Request, count: int = Query(default=1, ge=1)) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "element or elements is required"}, status_code=422)
        if "elements" in body:
            elements = body.get("elements")
            if not isinstance(elements, list):
                return JSONResponse({"error": "elements must be a list"}, status_code=422)
            for element in elements:
                misra.update(str(element), count)
            updated = len(elements)
        elif "element" in body:
            misra.update(str(body.get("element")), count)
            updated = 1
        else:
            return JSONResponse({"error": "element or elements is required"}, status_code=422)
        return JSONResponse({"updated": updated, "n": misra.n})

    @app.get("/api/v1/misragries/estimate")
    async def api_mg_estimate(element: str) -> JSONResponse:
        return JSONResponse({"element": element, "estimate": misra.estimate(element)})

    @app.get("/api/v1/misragries/heavy_hitters")
    async def api_mg_heavy_hitters(support: float = Query(gt=0.0, le=1.0)) -> JSONResponse:
        return JSONResponse({"support": support, "heavy_hitters": misra.heavy_hitters(support)})

    @app.get("/api/v1/misragries/stats")
    async def api_mg_stats() -> JSONResponse:
        return JSONResponse(misra.stats())

    @app.post("/api/v1/misragries/reset")
    async def api_mg_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            misra.reset(body.get("k"))
        except MisraGriesError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(misra.stats())

    return misra
