"""Phase 104 — Sovereign Augmented Sketch HTTP routes.

Exposes an :class:`~pradyos.core.augmented_sketch.AugmentedSketch` over REST.
Routes are registered onto the FastAPI ``app`` built by
``sovereign_web.create_app()`` via :func:`register_augmentedsketch_routes`,
called *inside* the factory — the sketch lives in factory scope (passed in, or
created fresh per app), so there is no module-level singleton. All routes are
static (no path parameters), so none can shadow another. Items are normalised to
strings for transport.

Routes (mounted under ``/api/v1/augmentedsketch``):
  POST /api/v1/augmentedsketch/add    body ``{"item": x, "delta"?: d}`` — add occurrences, returns estimate
  GET  /api/v1/augmentedsketch/query  ``?item=x`` — frequency estimate (exact if tracked, else sketch median)
  GET  /api/v1/augmentedsketch/topk   ``?n=`` — augmentation-dict heavy hitters (defaults to k)
  GET  /api/v1/augmentedsketch/stats  ``{width, depth, k, seed, tracked, total}``
  POST /api/v1/augmentedsketch/reset  body ``{"width"?, "depth"?, "k"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.augmented_sketch import AugmentedSketch, AugmentedSketchError


def register_augmentedsketch_routes(app: Any, augmented: Any | None = None) -> Any:
    """Register the /api/v1/augmentedsketch routes on ``app``; return the sketch used.

    ``augmented`` defaults to a fresh :class:`AugmentedSketch` owned by this app
    instance (factory scope — never a module-level global)."""
    if augmented is None:
        augmented = AugmentedSketch()

    @app.post("/api/v1/augmentedsketch/add")
    async def api_as_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        delta = body.get("delta", 1)
        try:
            estimate = augmented.add(str(body["item"]), delta)
        except AugmentedSketchError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"item": str(body["item"]), "delta": delta, "estimate": estimate})

    @app.get("/api/v1/augmentedsketch/query")
    async def api_as_query(item: str) -> JSONResponse:
        return JSONResponse({"item": item, "count": augmented.query(item)})

    @app.get("/api/v1/augmentedsketch/topk")
    async def api_as_topk(n: int | None = Query(default=None, ge=1)) -> JSONResponse:
        top = augmented.top_k(n)
        return JSONResponse({"topk": [{"item": it, "count": c} for it, c in top]})

    @app.get("/api/v1/augmentedsketch/stats")
    async def api_as_stats() -> JSONResponse:
        return JSONResponse(augmented.stats())

    @app.post("/api/v1/augmentedsketch/reset")
    async def api_as_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            augmented.reset(body.get("width"), body.get("depth"), body.get("k"), body.get("seed"))
        except AugmentedSketchError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(augmented.stats())

    return augmented
