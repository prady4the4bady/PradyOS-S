"""Phase 130 — Sovereign AMS / tug-of-war F₂-sketch HTTP routes.

Exposes an :class:`~pradyos.core.ams_sketch.AMSSketch` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_ams_routes`,
called *inside* the factory — the sketch lives in factory scope (passed in, or created fresh
per app), so there is no module-level singleton. All routes are static (no path parameters),
so none can shadow another.

A wrong-type key/count or configuration is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/ams``):
  POST   /api/v1/ams/update       body ``{"key": ..., "count"?: int}`` — ``{key, f2}``
  POST   /api/v1/ams/update_many  body ``{"keys": [...]}`` — ``{added, f2}``
  GET    /api/v1/ams/f2            ``{f2, l2_norm}``
  GET    /api/v1/ams/stats         ``{width, depth, f2, l2_norm, standard_error, seed}``
  DELETE /api/v1/ams/reset         body ``{"width"?, "depth"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.ams_sketch import AMSSketch, AMSError


def register_ams_routes(app: Any, ams: Any | None = None) -> Any:
    """Register the /api/v1/ams routes on ``app``; return the sketch used.

    ``ams`` defaults to a fresh :class:`AMSSketch` owned by this app instance
    (factory scope — never a module-level global)."""
    if ams is None:
        ams = AMSSketch()

    @app.post("/api/v1/ams/update")
    async def api_ams_update(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        count = body.get("count", 1)
        try:
            ams.update(body["key"], count)
        except AMSError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "f2": ams.stats()["f2"]})

    @app.post("/api/v1/ams/update_many")
    async def api_ams_update_many(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("keys"), list):
            return JSONResponse({"error": "keys list is required"}, status_code=422)
        try:
            added = ams.update_many(body["keys"])
        except AMSError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"added": added, "f2": ams.stats()["f2"]})

    @app.get("/api/v1/ams/f2")
    async def api_ams_f2() -> JSONResponse:
        s = ams.stats()
        return JSONResponse({"f2": s["f2"], "l2_norm": s["l2_norm"]})

    @app.get("/api/v1/ams/stats")
    async def api_ams_stats() -> JSONResponse:
        return JSONResponse(ams.stats())

    @app.delete("/api/v1/ams/reset")
    async def api_ams_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            ams.reset(body.get("width"), body.get("depth"), body.get("seed"))
        except AMSError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(ams.stats())

    return ams
