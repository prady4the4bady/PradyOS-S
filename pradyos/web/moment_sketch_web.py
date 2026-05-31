"""Phase 106 — Sovereign Moment Sketch HTTP routes.

Exposes a :class:`~pradyos.core.moment_sketch.MomentSketch` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_momentsketch_routes`, called *inside* the factory — the sketch
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Routes (mounted under ``/api/v1/momentsketch``):
  POST   /api/v1/momentsketch/add       body ``{"value": x}`` — add a value
  GET    /api/v1/momentsketch/quantile  ``?q=`` — MaxEnt-reconstructed quantile (q in (0,1))
  POST   /api/v1/momentsketch/merge     body ``{"moments": [...], "min_val", "max_val", "k"?}`` — merge a serialized state
  GET    /api/v1/momentsketch/stats     ``{k, seed, total_count, min_val, max_val, moments}``
  DELETE /api/v1/momentsketch/reset     body ``{"k"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.moment_sketch import MomentSketch, MomentSketchError


def register_momentsketch_routes(app: Any, sketch: Any | None = None) -> Any:
    """Register the /api/v1/momentsketch routes on ``app``; return the sketch used.

    ``sketch`` defaults to a fresh :class:`MomentSketch` owned by this app
    instance (factory scope — never a module-level global)."""
    if sketch is None:
        sketch = MomentSketch()

    @app.post("/api/v1/momentsketch/add")
    async def api_ms_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            sketch.add(body["value"])
        except MomentSketchError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "total_count": sketch.total_count})

    @app.get("/api/v1/momentsketch/quantile")
    async def api_ms_quantile(q: float = Query(gt=0.0, lt=1.0)) -> JSONResponse:
        try:
            value = sketch.quantile(q)
        except MomentSketchError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"q": q, "value": value})

    @app.post("/api/v1/momentsketch/merge")
    async def api_ms_merge(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("moments"), list):
            return JSONResponse({"error": "serialized state with 'moments' list is required"},
                                status_code=422)
        try:
            sketch.merge_state(body)
        except MomentSketchError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(sketch.stats())

    @app.get("/api/v1/momentsketch/stats")
    async def api_ms_stats() -> JSONResponse:
        return JSONResponse(sketch.stats())

    @app.delete("/api/v1/momentsketch/reset")
    async def api_ms_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            sketch.reset(body.get("k"), body.get("seed"))
        except MomentSketchError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(sketch.stats())

    return sketch
