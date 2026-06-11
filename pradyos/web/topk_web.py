"""Phase 87 — Sovereign Top-K (Space-Saving) HTTP routes.

Exposes a :class:`~pradyos.core.space_saving.SpaceSaving` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_topk_routes`, called *inside* the factory — the sketch lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

Where Phase 76's Count-Min Sketch answers "how often did X appear?", this answers
"what are the top K items?" — the ranking half of the approximate-frequency stack.

Routes (mounted under ``/api/v1/topk``):
  POST /api/v1/topk/insert   body ``{"item": any}`` or ``{"items": [...]}``
  GET  /api/v1/topk/query    ``?n=N`` — the top-N leaderboard (omit N for all)
  GET  /api/v1/topk/stats    ``{k, monitored, total, min_count}``
  POST /api/v1/topk/reset    body ``{"k"?: int}`` — clear / resize
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.space_saving import SpaceSaving, SpaceSavingError

DEFAULT_K = 10


def register_topk_routes(app: Any, space_saving: Any | None = None) -> Any:
    """Register the /api/v1/topk routes on ``app``; return the sketch used.

    ``space_saving`` defaults to a fresh :class:`SpaceSaving` owned by this app
    instance (factory scope — never a module-level global)."""
    if space_saving is None:
        space_saving = SpaceSaving(DEFAULT_K)

    @app.post("/api/v1/topk/insert")
    async def api_topk_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "item or items is required"}, status_code=422)
        try:
            if "items" in body:
                items = body.get("items")
                if not isinstance(items, list):
                    return JSONResponse({"error": "items must be a list"}, status_code=422)
                added = space_saving.add_many(items)
            elif "item" in body:
                space_saving.add(body.get("item"))
                added = 1
            else:
                return JSONResponse({"error": "item or items is required"}, status_code=422)
        except TypeError:
            return JSONResponse({"error": "item must be hashable"}, status_code=422)
        return JSONResponse(
            {"inserted": added, "total": space_saving.total, "monitored": len(space_saving)}
        )

    @app.get("/api/v1/topk/query")
    async def api_topk_query(n: int | None = Query(default=None, ge=0)) -> JSONResponse:
        top = space_saving.top(n)
        return JSONResponse({"top": top, "n": len(top)})

    @app.get("/api/v1/topk/stats")
    async def api_topk_stats() -> JSONResponse:
        return JSONResponse(space_saving.stats())

    @app.post("/api/v1/topk/reset")
    async def api_topk_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        k = body.get("k") if isinstance(body, dict) else None
        try:
            space_saving.reset(k)
        except SpaceSavingError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(space_saving.stats())

    return space_saving
