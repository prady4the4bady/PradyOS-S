"""Phase 165 — Sovereign Heavy-Light Decomposition HTTP routes.

Exposes a :class:`~pradyos.core.heavy_light.HeavyLight` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_hld_routes`, called
*inside* the factory — the structure lives in factory scope (passed in, or created fresh per app),
so there is no module-level singleton. All routes are static (no path parameters), so none can
shadow another.

A malformed parent array (multiple roots / cycle / out-of-range), a values-length mismatch, an
out-of-range node, or a non-numeric value is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/hld``):
  POST   /api/v1/hld/build        body ``{"parents": [...], "values"?: [...]}`` — rebuild, returns stats
  POST   /api/v1/hld/update       body ``{"node", "value"}`` — ``{node, value, total}``
  GET    /api/v1/hld/path_sum     query ``?u=&v=`` — ``{u, v, sum}``
  GET    /api/v1/hld/path_max     query ``?u=&v=`` — ``{u, v, max}``
  GET    /api/v1/hld/subtree_sum  query ``?v=`` — ``{v, sum}``
  GET    /api/v1/hld/depth        query ``?v=`` — ``{v, depth}``
  GET    /api/v1/hld/stats         ``{size, total, max, num_chains}``
  DELETE /api/v1/hld/reset         discard the tree
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.heavy_light import HeavyLight, HeavyLightError


def register_hld_routes(app: Any, heavy_light: Any | None = None) -> Any:
    """Register the /api/v1/hld routes on ``app``; return the structure used.

    ``heavy_light`` defaults to a fresh empty :class:`HeavyLight` owned by this app instance
    (factory scope — never a module-level global)."""
    if heavy_light is None:
        heavy_light = HeavyLight()
    hl = heavy_light

    @app.post("/api/v1/hld/build")
    async def api_hld_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "parents" not in body:
            return JSONResponse({"error": "parents is required"}, status_code=422)
        try:
            hl.build(body["parents"], body.get("values"))
        except HeavyLightError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(hl.stats())

    @app.post("/api/v1/hld/update")
    async def api_hld_update(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "node" not in body or "value" not in body:
            return JSONResponse({"error": "node and value are required"}, status_code=422)
        try:
            hl.update(body["node"], body["value"])
        except HeavyLightError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"node": body["node"], "value": body["value"], "total": hl.stats()["total"]})

    @app.get("/api/v1/hld/path_sum")
    async def api_hld_path_sum(u: int = Query(..., ge=0), v: int = Query(..., ge=0)) -> JSONResponse:
        try:
            s = hl.path_sum(u, v)
        except HeavyLightError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"u": u, "v": v, "sum": s})

    @app.get("/api/v1/hld/path_max")
    async def api_hld_path_max(u: int = Query(..., ge=0), v: int = Query(..., ge=0)) -> JSONResponse:
        try:
            m = hl.path_max(u, v)
        except HeavyLightError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"u": u, "v": v, "max": m})

    @app.get("/api/v1/hld/subtree_sum")
    async def api_hld_subtree(v: int = Query(..., ge=0)) -> JSONResponse:
        try:
            s = hl.subtree_sum(v)
        except HeavyLightError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"v": v, "sum": s})

    @app.get("/api/v1/hld/depth")
    async def api_hld_depth(v: int = Query(..., ge=0)) -> JSONResponse:
        try:
            d = hl.depth(v)
        except HeavyLightError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"v": v, "depth": d})

    @app.get("/api/v1/hld/stats")
    async def api_hld_stats() -> JSONResponse:
        return JSONResponse(hl.stats())

    @app.delete("/api/v1/hld/reset")
    async def api_hld_reset() -> JSONResponse:
        hl.reset()
        return JSONResponse(hl.stats())

    return hl
