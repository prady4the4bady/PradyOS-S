"""Phase 127 — Sovereign Random Projection / JL sketch HTTP routes.

Exposes a :class:`~pradyos.core.random_projection.RandomProjection` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_randomprojection_routes`, called *inside* the factory — the random matrix
lives in factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

A wrong-dimension or non-numeric vector is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/randomprojection``):
  POST   /api/v1/randomprojection/project   body ``{"vector": [...]}`` — ``{projection, output_dim}``
  POST   /api/v1/randomprojection/distance  body ``{"a": [...], "b": [...]}`` — estimated ``‖a − b‖``
  POST   /api/v1/randomprojection/dot       body ``{"a": [...], "b": [...]}`` — estimated ``⟨a, b⟩``
  GET    /api/v1/randomprojection/stats      ``{input_dim, output_dim, compression_ratio, seed}``
  DELETE /api/v1/randomprojection/reset      body ``{"input_dim"?, "output_dim"?, "seed"?}`` — redraw / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.random_projection import RandomProjection, RandomProjectionError


def register_randomprojection_routes(app: Any, random_projection: Any | None = None) -> Any:
    """Register the /api/v1/randomprojection routes on ``app``; return the projector used.

    ``random_projection`` defaults to a fresh :class:`RandomProjection` owned by this app
    instance (factory scope — never a module-level global)."""
    if random_projection is None:
        random_projection = RandomProjection()

    @app.post("/api/v1/randomprojection/project")
    async def api_rp_project(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("vector"), list):
            return JSONResponse({"error": "vector list is required"}, status_code=422)
        try:
            proj = random_projection.project(body["vector"])
        except RandomProjectionError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"projection": proj, "output_dim": random_projection.output_dim})

    @app.post("/api/v1/randomprojection/distance")
    async def api_rp_distance(request: Request) -> JSONResponse:
        body = await request.json()
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("a"), list)
            or not isinstance(body.get("b"), list)
        ):
            return JSONResponse({"error": "a and b vector lists are required"}, status_code=422)
        try:
            d = random_projection.distance(body["a"], body["b"])
        except RandomProjectionError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"distance": d})

    @app.post("/api/v1/randomprojection/dot")
    async def api_rp_dot(request: Request) -> JSONResponse:
        body = await request.json()
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("a"), list)
            or not isinstance(body.get("b"), list)
        ):
            return JSONResponse({"error": "a and b vector lists are required"}, status_code=422)
        try:
            d = random_projection.dot(body["a"], body["b"])
        except RandomProjectionError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"dot": d})

    @app.get("/api/v1/randomprojection/stats")
    async def api_rp_stats() -> JSONResponse:
        return JSONResponse(random_projection.stats())

    @app.delete("/api/v1/randomprojection/reset")
    async def api_rp_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            random_projection.reset(body.get("input_dim"), body.get("output_dim"), body.get("seed"))
        except RandomProjectionError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(random_projection.stats())

    return random_projection
