"""Phase 167 — Sovereign Convex Hull HTTP routes.

Exposes a :class:`~pradyos.core.convex_hull.ConvexHull` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_convexhull_routes`,
called *inside* the factory — the hull lives in factory scope (passed in, or created fresh per app),
so there is no module-level singleton. All routes are static (no path parameters), so none can
shadow another.

A malformed point list or a non-numeric query point is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/convexhull``):
  POST   /api/v1/convexhull/build     body ``{"points": [[x, y], ...]}`` — rebuild, returns stats
  GET    /api/v1/convexhull/hull       ``{hull, num_hull_points}``  (CCW vertices)
  GET    /api/v1/convexhull/contains  query ``?x=&y=`` — ``{x, y, contains}``
  GET    /api/v1/convexhull/stats      ``{num_points, num_hull_points, area, perimeter}``
  DELETE /api/v1/convexhull/reset      discard all points
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.convex_hull import ConvexHull, ConvexHullError


def register_convexhull_routes(app: Any, convex_hull: Any | None = None) -> Any:
    """Register the /api/v1/convexhull routes on ``app``; return the hull used.

    ``convex_hull`` defaults to a fresh empty :class:`ConvexHull` owned by this app instance
    (factory scope — never a module-level global)."""
    if convex_hull is None:
        convex_hull = ConvexHull()
    ch = convex_hull

    @app.post("/api/v1/convexhull/build")
    async def api_ch_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "points" not in body:
            return JSONResponse({"error": "points is required"}, status_code=422)
        try:
            ch.build(body["points"])
        except ConvexHullError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(ch.stats())

    @app.get("/api/v1/convexhull/hull")
    async def api_ch_hull() -> JSONResponse:
        verts = [list(p) for p in ch.hull()]
        return JSONResponse({"hull": verts, "num_hull_points": len(verts)})

    @app.get("/api/v1/convexhull/contains")
    async def api_ch_contains(x: float = Query(...), y: float = Query(...)) -> JSONResponse:
        try:
            present = ch.contains(x, y)
        except ConvexHullError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"x": x, "y": y, "contains": present})

    @app.get("/api/v1/convexhull/stats")
    async def api_ch_stats() -> JSONResponse:
        return JSONResponse(ch.stats())

    @app.delete("/api/v1/convexhull/reset")
    async def api_ch_reset() -> JSONResponse:
        ch.reset()
        return JSONResponse(ch.stats())

    return ch
