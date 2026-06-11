"""Phase 168 — Sovereign Polygon HTTP routes.

Exposes a :class:`~pradyos.core.polygon.Polygon` over REST. Routes are registered onto the FastAPI
``app`` built by ``sovereign_web.create_app()`` via :func:`register_polygon_routes`, called *inside*
the factory — the polygon lives in factory scope (passed in, or created fresh per app), so there is
no module-level singleton. All routes are static (no path parameters), so none can shadow another.

A malformed vertex list or a non-numeric query point is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/polygon``):
  POST   /api/v1/polygon/build     body ``{"vertices": [[x, y], ...]}`` — rebuild (order preserved), returns stats
  GET    /api/v1/polygon/contains  query ``?x=&y=`` — ``{x, y, contains}``  (ray casting)
  GET    /api/v1/polygon/stats      ``{num_vertices, area, perimeter, is_convex, orientation}``
  GET    /api/v1/polygon/centroid   ``{centroid}``  (``[cx, cy]`` or ``null`` when empty)
  DELETE /api/v1/polygon/reset      discard all vertices
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.polygon import Polygon, PolygonError


def register_polygon_routes(app: Any, polygon: Any | None = None) -> Any:
    """Register the /api/v1/polygon routes on ``app``; return the polygon used.

    ``polygon`` defaults to a fresh empty :class:`Polygon` owned by this app instance
    (factory scope — never a module-level global)."""
    if polygon is None:
        polygon = Polygon()
    poly = polygon

    @app.post("/api/v1/polygon/build")
    async def api_poly_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "vertices" not in body:
            return JSONResponse({"error": "vertices is required"}, status_code=422)
        try:
            poly.build(body["vertices"])
        except PolygonError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(poly.stats())

    @app.get("/api/v1/polygon/contains")
    async def api_poly_contains(x: float = Query(...), y: float = Query(...)) -> JSONResponse:
        try:
            present = poly.contains(x, y)
        except PolygonError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"x": x, "y": y, "contains": present})

    @app.get("/api/v1/polygon/stats")
    async def api_poly_stats() -> JSONResponse:
        return JSONResponse(poly.stats())

    @app.get("/api/v1/polygon/centroid")
    async def api_poly_centroid() -> JSONResponse:
        c = poly.centroid()
        return JSONResponse({"centroid": list(c) if c is not None else None})

    @app.delete("/api/v1/polygon/reset")
    async def api_poly_reset() -> JSONResponse:
        poly.reset()
        return JSONResponse(poly.stats())

    return poly
