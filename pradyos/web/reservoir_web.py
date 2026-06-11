"""Phase 85 — Sovereign Reservoir Sampler HTTP routes.

Exposes a :class:`~pradyos.core.reservoir.SovereignReservoir` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()``
via :func:`register_reservoir_routes`, called *inside* the factory — the sampler
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Routes (mounted under ``/api/v1/reservoir``):
  POST /api/v1/reservoir/feed    body ``{"items": [...]}`` or ``{"item": any}``
  GET  /api/v1/reservoir/sample  current reservoir contents
  POST /api/v1/reservoir/reset   body ``{"capacity"?: int}`` — clear / resize
  GET  /api/v1/reservoir/stats   ``{capacity, seen, filled}``
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.reservoir import ReservoirError, SovereignReservoir

DEFAULT_CAPACITY = 16


def register_reservoir_routes(app: Any, reservoir: Any | None = None) -> Any:
    """Register the /api/v1/reservoir routes on ``app``; return the sampler used.

    ``reservoir`` defaults to a fresh :class:`SovereignReservoir` owned by this
    app instance (factory scope — never a module-level global)."""
    if reservoir is None:
        reservoir = SovereignReservoir(DEFAULT_CAPACITY)

    @app.post("/api/v1/reservoir/feed")
    async def api_reservoir_feed(request: Request) -> JSONResponse:
        body = await request.json()
        if "items" in body:
            items = body.get("items")
            if not isinstance(items, list):
                return JSONResponse({"error": "items must be a list"}, status_code=422)
            fed = reservoir.feed_many(items)
        elif "item" in body:
            reservoir.feed(body.get("item"))
            fed = 1
        else:
            return JSONResponse({"error": "item or items is required"}, status_code=422)
        return JSONResponse({"fed": fed, "seen": reservoir.seen, "filled": len(reservoir)})

    @app.get("/api/v1/reservoir/sample")
    async def api_reservoir_sample() -> JSONResponse:
        items = reservoir.sample()
        return JSONResponse({"sample": items, "size": len(items)})

    @app.post("/api/v1/reservoir/reset")
    async def api_reservoir_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        capacity = body.get("capacity") if isinstance(body, dict) else None
        try:
            reservoir.reset(capacity)
        except ReservoirError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(
            {"capacity": reservoir.capacity, "seen": reservoir.seen, "filled": len(reservoir)}
        )

    @app.get("/api/v1/reservoir/stats")
    async def api_reservoir_stats() -> JSONResponse:
        return JSONResponse(reservoir.stats())

    return reservoir
