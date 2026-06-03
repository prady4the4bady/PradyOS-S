"""Phase 129 — Sovereign Flajolet–Martin / PCSA cardinality-sketch HTTP routes.

Exposes a :class:`~pradyos.core.fm_sketch.FMSketch` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_fmsketch_routes`,
called *inside* the factory — the sketch lives in factory scope (passed in, or created fresh
per app), so there is no module-level singleton. All routes are static (no path parameters),
so none can shadow another.

A wrong-type item or configuration is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/fmsketch``):
  POST   /api/v1/fmsketch/add       body ``{"item": ...}`` — ``{item, estimate}``
  POST   /api/v1/fmsketch/add_many  body ``{"items": [...]}`` — ``{added, estimate}``
  GET    /api/v1/fmsketch/estimate   ``{estimate, count}``
  GET    /api/v1/fmsketch/stats      ``{num_bitmaps, num_bits, estimate, standard_error, seed}``
  DELETE /api/v1/fmsketch/reset      body ``{"num_bitmaps"?, "num_bits"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.fm_sketch import FMSketch, FMSketchError


def register_fmsketch_routes(app: Any, fm_sketch: Any | None = None) -> Any:
    """Register the /api/v1/fmsketch routes on ``app``; return the sketch used.

    ``fm_sketch`` defaults to a fresh :class:`FMSketch` owned by this app instance
    (factory scope — never a module-level global)."""
    if fm_sketch is None:
        fm_sketch = FMSketch()

    @app.post("/api/v1/fmsketch/add")
    async def api_fm_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        try:
            fm_sketch.add(body["item"])
        except FMSketchError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"item": body["item"], "estimate": fm_sketch.stats()["estimate"]})

    @app.post("/api/v1/fmsketch/add_many")
    async def api_fm_add_many(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            return JSONResponse({"error": "items list is required"}, status_code=422)
        try:
            added = fm_sketch.add_many(body["items"])
        except FMSketchError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"added": added, "estimate": fm_sketch.stats()["estimate"]})

    @app.get("/api/v1/fmsketch/estimate")
    async def api_fm_estimate() -> JSONResponse:
        return JSONResponse({"estimate": fm_sketch.stats()["estimate"], "count": fm_sketch.count()})

    @app.get("/api/v1/fmsketch/stats")
    async def api_fm_stats() -> JSONResponse:
        return JSONResponse(fm_sketch.stats())

    @app.delete("/api/v1/fmsketch/reset")
    async def api_fm_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            fm_sketch.reset(body.get("num_bitmaps"), body.get("num_bits"), body.get("seed"))
        except FMSketchError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(fm_sketch.stats())

    return fm_sketch
