"""Phase 139 — Sovereign KD-Tree HTTP routes.

Exposes a :class:`~pradyos.core.kd_tree.KDTree` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_kdtree_routes`,
called *inside* the factory — the tree lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. ``build`` may re-create the tree at a new
dimension, so the routes share a small ``state`` holder. All routes are static (no path
parameters), so none can shadow another.

A wrong-dimension / non-numeric point, bad ``dim``, or ``lo > hi`` box is a request error →
**HTTP 422**.

Routes (mounted under ``/api/v1/kdtree``):
  POST   /api/v1/kdtree/build    body ``{"points": [[...],...], "dim"?}`` — returns stats
  POST   /api/v1/kdtree/nearest  body ``{"point": [...]}`` — ``{point, nearest, distance}``
  POST   /api/v1/kdtree/range    body ``{"lo": [...], "hi": [...]}`` — ``{lo, hi, points, count}``
  GET    /api/v1/kdtree/stats     ``{size, dim, height}``
  DELETE /api/v1/kdtree/reset     (no body) — clear (keeps dim)
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.kd_tree import KDTree, KDTreeError


def register_kdtree_routes(app: Any, kd_tree: Any | None = None) -> Any:
    """Register the /api/v1/kdtree routes on ``app``; return the tree used.

    ``kd_tree`` defaults to a fresh (empty, 2-D) :class:`KDTree` owned by this app instance
    (factory scope — never a module-level global)."""
    if kd_tree is None:
        kd_tree = KDTree(dim=2)
    state = {"tree": kd_tree}  # holder: build may swap in a new-dimension tree

    @app.post("/api/v1/kdtree/build")
    async def api_kd_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("points"), list):
            return JSONResponse({"error": "points list is required"}, status_code=422)
        dim = body.get("dim", state["tree"].dim)
        try:
            state["tree"] = KDTree(body["points"], dim=dim)
        except KDTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(state["tree"].stats())

    @app.post("/api/v1/kdtree/nearest")
    async def api_kd_nearest(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("point"), list):
            return JSONResponse({"error": "point list is required"}, status_code=422)
        tree = state["tree"]
        try:
            nearest = tree.nearest(body["point"])
            dist = tree.nearest_dist(body["point"])
        except KDTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(
            {
                "point": body["point"],
                "nearest": list(nearest) if nearest is not None else None,
                "distance": dist,
            }
        )

    @app.post("/api/v1/kdtree/range")
    async def api_kd_range(request: Request) -> JSONResponse:
        body = await request.json()
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("lo"), list)
            or not isinstance(body.get("hi"), list)
        ):
            return JSONResponse({"error": "lo and hi lists are required"}, status_code=422)
        try:
            hits = state["tree"].range(body["lo"], body["hi"])
        except KDTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(
            {
                "lo": body["lo"],
                "hi": body["hi"],
                "points": [list(p) for p in hits],
                "count": len(hits),
            }
        )

    @app.get("/api/v1/kdtree/stats")
    async def api_kd_stats() -> JSONResponse:
        return JSONResponse(state["tree"].stats())

    @app.delete("/api/v1/kdtree/reset")
    async def api_kd_reset() -> JSONResponse:
        state["tree"].reset()
        return JSONResponse(state["tree"].stats())

    return kd_tree
