"""Phase 146 — Sovereign 2D Fenwick Tree HTTP routes.

Exposes a :class:`~pradyos.core.fenwick_2d.Fenwick2D` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_fenwick2d_routes`,
called *inside* the factory — the grid lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so
none can shadow another.

An out-of-range coordinate, ``r1 > r2`` / ``c1 > c2``, or non-numeric delta is a request error
→ **HTTP 422** (query coordinates use the ``Query(ge=0)`` idiom; the grid-bound and ordering
rules are caught from the core).

Routes (mounted under ``/api/v1/fenwick2d``):
  POST   /api/v1/fenwick2d/update       body ``{"i", "j", "delta"}`` — ``{i, j, total}``
  GET    /api/v1/fenwick2d/prefix_sum   query ``?i=&j=`` — ``{i, j, sum}``
  GET    /api/v1/fenwick2d/range_sum    query ``?r1=&c1=&r2=&c2=`` — ``{sum}``
  GET    /api/v1/fenwick2d/point_value  query ``?i=&j=`` — ``{i, j, value}``
  GET    /api/v1/fenwick2d/stats         ``{rows, cols, cells, total}``
  DELETE /api/v1/fenwick2d/reset         body ``{"rows"?, "cols"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.fenwick_2d import Fenwick2D, Fenwick2DError


def register_fenwick2d_routes(app: Any, fenwick2d: Any | None = None) -> Any:
    """Register the /api/v1/fenwick2d routes on ``app``; return the grid used.

    ``fenwick2d`` defaults to a fresh 16×16 :class:`Fenwick2D` owned by this app instance
    (factory scope — never a module-level global)."""
    if fenwick2d is None:
        fenwick2d = Fenwick2D()

    @app.post("/api/v1/fenwick2d/update")
    async def api_f2_update(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "i" not in body or "j" not in body or "delta" not in body:
            return JSONResponse({"error": "i, j and delta are required"}, status_code=422)
        try:
            fenwick2d.update(body["i"], body["j"], body["delta"])
        except Fenwick2DError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": body["i"], "j": body["j"], "total": fenwick2d.total()})

    @app.get("/api/v1/fenwick2d/prefix_sum")
    async def api_f2_prefix(i: int = Query(..., ge=0), j: int = Query(..., ge=0)) -> JSONResponse:
        try:
            s = fenwick2d.prefix_sum(i, j)
        except Fenwick2DError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": i, "j": j, "sum": s})

    @app.get("/api/v1/fenwick2d/range_sum")
    async def api_f2_range(
        r1: int = Query(..., ge=0),
        c1: int = Query(..., ge=0),
        r2: int = Query(..., ge=0),
        c2: int = Query(..., ge=0),
    ) -> JSONResponse:
        try:
            s = fenwick2d.range_sum(r1, c1, r2, c2)
        except Fenwick2DError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"r1": r1, "c1": c1, "r2": r2, "c2": c2, "sum": s})

    @app.get("/api/v1/fenwick2d/point_value")
    async def api_f2_point(i: int = Query(..., ge=0), j: int = Query(..., ge=0)) -> JSONResponse:
        try:
            v = fenwick2d.point_value(i, j)
        except Fenwick2DError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": i, "j": j, "value": v})

    @app.get("/api/v1/fenwick2d/stats")
    async def api_f2_stats() -> JSONResponse:
        return JSONResponse(fenwick2d.stats())

    @app.delete("/api/v1/fenwick2d/reset")
    async def api_f2_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            fenwick2d.reset(body.get("rows"), body.get("cols"))
        except Fenwick2DError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(fenwick2d.stats())

    return fenwick2d
