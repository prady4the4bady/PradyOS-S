"""Phase 137 — Sovereign Interval Tree HTTP routes.

Exposes an :class:`~pradyos.core.interval_tree.IntervalTree` over REST. Routes are registered
onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_intervaltree_routes`, called *inside* the factory — the tree lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton. All routes
are static (no path parameters), so none can shadow another.

A non-numeric endpoint or ``low > high`` is a request error → **HTTP 422** (query endpoints use
``Query`` float params; the ``low ≤ high`` rule is caught from the core). ``overlap_any`` and
``contains`` remain on the core class (not mounted).

Routes (mounted under ``/api/v1/intervaltree``):
  POST   /api/v1/intervaltree/insert   body ``{"low", "high"}`` — ``{low, high, size}``
  DELETE /api/v1/intervaltree/remove   body ``{"low", "high"}`` — ``{low, high, removed, size}``
  GET    /api/v1/intervaltree/overlap  query ``?low=&high=`` — ``{low, high, intervals, count}``
  GET    /api/v1/intervaltree/stab     query ``?point=`` — ``{point, intervals, count}``
  GET    /api/v1/intervaltree/stats     ``{size, max_endpoint, height}``
  DELETE /api/v1/intervaltree/reset     (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.interval_tree import IntervalTree, IntervalTreeError


def register_intervaltree_routes(app: Any, interval_tree: Any | None = None) -> Any:
    """Register the /api/v1/intervaltree routes on ``app``; return the tree used.

    ``interval_tree`` defaults to a fresh (empty) :class:`IntervalTree` owned by this app
    instance (factory scope — never a module-level global)."""
    if interval_tree is None:
        interval_tree = IntervalTree()

    @app.post("/api/v1/intervaltree/insert")
    async def api_iv_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "low" not in body or "high" not in body:
            return JSONResponse({"error": "low and high are required"}, status_code=422)
        try:
            interval_tree.insert(body["low"], body["high"])
        except IntervalTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"low": body["low"], "high": body["high"], "size": len(interval_tree)})

    @app.delete("/api/v1/intervaltree/remove")
    async def api_iv_remove(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "low" not in body or "high" not in body:
            return JSONResponse({"error": "low and high are required"}, status_code=422)
        try:
            removed = interval_tree.remove(body["low"], body["high"])
        except IntervalTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(
            {
                "low": body["low"],
                "high": body["high"],
                "removed": removed,
                "size": len(interval_tree),
            }
        )

    @app.get("/api/v1/intervaltree/overlap")
    async def api_iv_overlap(low: float = Query(...), high: float = Query(...)) -> JSONResponse:
        try:
            hits = interval_tree.overlap(low, high)
        except IntervalTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(
            {"low": low, "high": high, "intervals": [list(iv) for iv in hits], "count": len(hits)}
        )

    @app.get("/api/v1/intervaltree/stab")
    async def api_iv_stab(point: float = Query(...)) -> JSONResponse:
        try:
            hits = interval_tree.stab(point)
        except IntervalTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(
            {"point": point, "intervals": [list(iv) for iv in hits], "count": len(hits)}
        )

    @app.get("/api/v1/intervaltree/stats")
    async def api_iv_stats() -> JSONResponse:
        return JSONResponse(interval_tree.stats())

    @app.delete("/api/v1/intervaltree/reset")
    async def api_iv_reset() -> JSONResponse:
        interval_tree.reset()
        return JSONResponse(interval_tree.stats())

    return interval_tree
