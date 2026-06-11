"""Phase 102 — Sovereign HeavyKeeper HTTP routes.

Exposes a :class:`~pradyos.core.heavykeeper.HeavyKeeper` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_heavykeeper_routes`, called *inside* the factory — the sketch
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another. Items are normalised to strings for transport.

Routes (mounted under ``/api/v1/heavykeeper``):
  POST /api/v1/heavykeeper/add    body ``{"item": x, "count"?: c}`` — add occurrences, returns estimate
  GET  /api/v1/heavykeeper/topk   ``?n=`` — current heavy hitters (defaults to k)
  GET  /api/v1/heavykeeper/stats  ``{k, width, depth, decay, seed, tracked, total}``
  POST /api/v1/heavykeeper/reset  body ``{"k"?, "width"?, "depth"?, "decay"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.heavykeeper import HeavyKeeper, HeavyKeeperError


def register_heavykeeper_routes(app: Any, heavykeeper: Any | None = None) -> Any:
    """Register the /api/v1/heavykeeper routes on ``app``; return the sketch used.

    ``heavykeeper`` defaults to a fresh :class:`HeavyKeeper` owned by this app
    instance (factory scope — never a module-level global)."""
    if heavykeeper is None:
        heavykeeper = HeavyKeeper()

    @app.post("/api/v1/heavykeeper/add")
    async def api_hk_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        count = body.get("count", 1)
        try:
            estimate = heavykeeper.add(str(body["item"]), count)
        except HeavyKeeperError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"item": str(body["item"]), "count": count, "estimate": estimate})

    @app.get("/api/v1/heavykeeper/topk")
    async def api_hk_topk(n: int | None = Query(default=None, ge=1)) -> JSONResponse:
        top = heavykeeper.top_k(n)
        return JSONResponse({"topk": [{"item": it, "count": c} for it, c in top]})

    @app.get("/api/v1/heavykeeper/stats")
    async def api_hk_stats() -> JSONResponse:
        return JSONResponse(heavykeeper.stats())

    @app.post("/api/v1/heavykeeper/reset")
    async def api_hk_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            heavykeeper.reset(
                body.get("k"),
                body.get("width"),
                body.get("depth"),
                body.get("decay"),
                body.get("seed"),
            )
        except HeavyKeeperError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(heavykeeper.stats())

    return heavykeeper
