"""Phase 153 — Sovereign PR Quadtree HTTP routes.

Exposes a :class:`~pradyos.core.pr_quadtree.PRQuadtree` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_pr_quadtree_routes`,
called *inside* the factory — the quadtree lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so none
can shadow another.

A non-numeric / out-of-bounds point, a missing field, or an inverted query rectangle is a request
error → **HTTP 422**. ``search`` / ``nearest`` return ``null`` when there is no such point.

Routes (mounted under ``/api/v1/prquadtree``):
  POST   /api/v1/prquadtree/insert       body ``{"point_id", "x", "y"}`` — ``{point_id, num_points}``
  POST   /api/v1/prquadtree/delete       body ``{"point_id"}`` — ``{point_id, deleted, num_points}``
  GET    /api/v1/prquadtree/search       query ``?x=&y=`` — ``{x, y, point_id}``  (may be null)
  GET    /api/v1/prquadtree/range_query  query ``?x_min=&y_min=&x_max=&y_max=`` — ``{ids, count}``
  GET    /api/v1/prquadtree/nearest      query ``?x=&y=`` — ``{x, y, nearest}``  (may be null)
  GET    /api/v1/prquadtree/stats         ``{num_points, num_nodes, max_depth_reached}``
  DELETE /api/v1/prquadtree/reset         clear all points
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.pr_quadtree import PRQuadtree, PRQuadtreeError


def register_pr_quadtree_routes(app: Any, pr_quadtree: Any | None = None) -> Any:
    """Register the /api/v1/prquadtree routes on ``app``; return the quadtree used.

    ``pr_quadtree`` defaults to a fresh :class:`PRQuadtree` over ``[0, 1000] × [0, 1000]`` owned by
    this app instance (factory scope — never a module-level global)."""
    if pr_quadtree is None:
        pr_quadtree = PRQuadtree(0, 0, 1000, 1000)
    qt = pr_quadtree

    @app.post("/api/v1/prquadtree/insert")
    async def api_qt_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if (
            not isinstance(body, dict)
            or "point_id" not in body
            or "x" not in body
            or "y" not in body
        ):
            return JSONResponse({"error": "point_id, x and y are required"}, status_code=422)
        try:
            qt.insert(body["point_id"], body["x"], body["y"])
        except PRQuadtreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"point_id": body["point_id"], "num_points": qt.num_points})

    @app.post("/api/v1/prquadtree/delete")
    async def api_qt_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "point_id" not in body:
            return JSONResponse({"error": "point_id is required"}, status_code=422)
        deleted = qt.delete(body["point_id"])
        return JSONResponse(
            {"point_id": body["point_id"], "deleted": deleted, "num_points": qt.num_points}
        )

    @app.get("/api/v1/prquadtree/search")
    async def api_qt_search(x: float = Query(...), y: float = Query(...)) -> JSONResponse:
        try:
            pid = qt.search(x, y)
        except PRQuadtreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"x": x, "y": y, "point_id": pid})

    @app.get("/api/v1/prquadtree/range_query")
    async def api_qt_range(
        x_min: float = Query(...),
        y_min: float = Query(...),
        x_max: float = Query(...),
        y_max: float = Query(...),
    ) -> JSONResponse:
        try:
            ids = qt.range_query(x_min, y_min, x_max, y_max)
        except PRQuadtreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"ids": ids, "count": len(ids)})

    @app.get("/api/v1/prquadtree/nearest")
    async def api_qt_nearest(x: float = Query(...), y: float = Query(...)) -> JSONResponse:
        try:
            pid = qt.nearest(x, y)
        except PRQuadtreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"x": x, "y": y, "nearest": pid})

    @app.get("/api/v1/prquadtree/stats")
    async def api_qt_stats() -> JSONResponse:
        return JSONResponse(qt.stats())

    @app.delete("/api/v1/prquadtree/reset")
    async def api_qt_reset() -> JSONResponse:
        qt.reset()
        return JSONResponse(qt.stats())

    return qt
