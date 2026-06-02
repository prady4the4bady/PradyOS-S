"""Phase 111 — Sovereign Morris Counter HTTP routes.

Exposes a :class:`~pradyos.core.morris_counter.MorrisCounter` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_morris_routes`, called *inside* the factory — the counter lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

Routes (mounted under ``/api/v1/morris``):
  POST   /api/v1/morris/increment  body ``{"times"?: int}`` — register events (default 1); 422 on bad ``times``
  GET    /api/v1/morris/estimate   ``{estimate, register}`` — current unbiased estimate
  GET    /api/v1/morris/stats      ``{register, estimate, increments, base, relative_error, seed}``
  DELETE /api/v1/morris/reset      body ``{"base"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.morris_counter import MorrisCounter, MorrisCounterError


def register_morris_routes(app: Any, morris_counter: Any | None = None) -> Any:
    """Register the /api/v1/morris routes on ``app``; return the counter used.

    ``morris_counter`` defaults to a fresh :class:`MorrisCounter` owned by this app
    instance (factory scope — never a module-level global)."""
    if morris_counter is None:
        morris_counter = MorrisCounter()

    @app.post("/api/v1/morris/increment")
    async def api_morris_increment(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        times = body.get("times", 1)
        try:
            morris_counter.increment(times)
        except MorrisCounterError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({
            "register": morris_counter.register,
            "estimate": morris_counter.estimate(),
            "increments": morris_counter.increments,
        })

    @app.get("/api/v1/morris/estimate")
    async def api_morris_estimate() -> JSONResponse:
        return JSONResponse({
            "estimate": morris_counter.estimate(),
            "register": morris_counter.register,
        })

    @app.get("/api/v1/morris/stats")
    async def api_morris_stats() -> JSONResponse:
        return JSONResponse(morris_counter.stats())

    @app.delete("/api/v1/morris/reset")
    async def api_morris_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            morris_counter.reset(body.get("base"), body.get("seed"))
        except MorrisCounterError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(morris_counter.stats())

    return morris_counter
