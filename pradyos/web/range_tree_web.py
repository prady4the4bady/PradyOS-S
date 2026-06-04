"""Phase 157 — Sovereign Range Tree HTTP routes.

Exposes a :class:`~pradyos.core.range_tree.RangeTree` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_rangetree_routes`,
called *inside* the factory — the tree lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so none
can shadow another.

A malformed point list or an inverted query rectangle is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/rangetree``):
  POST   /api/v1/rangetree/build        body ``{"points": [[x, y], ...]}`` — rebuild, returns stats
  GET    /api/v1/rangetree/range_query  query ``?x_min=&y_min=&x_max=&y_max=`` — ``{points, count}``
  GET    /api/v1/rangetree/range_count  query ``?x_min=&y_min=&x_max=&y_max=`` — ``{count}``
  GET    /api/v1/rangetree/stats         ``{size, height, x_min, x_max}``
  DELETE /api/v1/rangetree/reset         clear all points
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.range_tree import RangeTree, RangeTreeError


def register_rangetree_routes(app: Any, range_tree: Any | None = None) -> Any:
    """Register the /api/v1/rangetree routes on ``app``; return the tree used.

    ``range_tree`` defaults to a fresh empty :class:`RangeTree` owned by this app instance
    (factory scope — never a module-level global)."""
    if range_tree is None:
        range_tree = RangeTree()
    rt = range_tree

    @app.post("/api/v1/rangetree/build")
    async def api_rt_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "points" not in body:
            return JSONResponse({"error": "points is required"}, status_code=422)
        try:
            rt.build(body["points"])
        except RangeTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(rt.stats())

    @app.get("/api/v1/rangetree/range_query")
    async def api_rt_range_query(x_min: float = Query(...), y_min: float = Query(...),
                                 x_max: float = Query(...), y_max: float = Query(...)) -> JSONResponse:
        try:
            pts = rt.range_query(x_min, y_min, x_max, y_max)
        except RangeTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"points": [list(p) for p in pts], "count": len(pts)})

    @app.get("/api/v1/rangetree/range_count")
    async def api_rt_range_count(x_min: float = Query(...), y_min: float = Query(...),
                                 x_max: float = Query(...), y_max: float = Query(...)) -> JSONResponse:
        try:
            c = rt.range_count(x_min, y_min, x_max, y_max)
        except RangeTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"count": c})

    @app.get("/api/v1/rangetree/stats")
    async def api_rt_stats() -> JSONResponse:
        return JSONResponse(rt.stats())

    @app.delete("/api/v1/rangetree/reset")
    async def api_rt_reset() -> JSONResponse:
        rt.reset()
        return JSONResponse(rt.stats())

    return rt
