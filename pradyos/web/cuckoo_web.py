"""Phase 86 — Sovereign Cuckoo Filter HTTP routes.

Exposes a :class:`~pradyos.core.cuckoo.SovereignCuckooFilter` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()``
via :func:`register_cuckoo_routes`, called *inside* the factory — the filter
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Unlike the Phase 72 Bloom filter, this one supports deletion (``DELETE /delete``).

Routes (mounted under ``/api/v1/cuckoo``):
  POST   /api/v1/cuckoo/insert    body ``{"item": any}`` — add one item
  POST   /api/v1/cuckoo/contains  body ``{"item": any}`` — membership check
  DELETE /api/v1/cuckoo/delete    body ``{"item": any}`` — remove one item
  GET    /api/v1/cuckoo/stats     ``{capacity, count, load_factor, ...}``
  POST   /api/v1/cuckoo/reset     clear all buckets
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.cuckoo import SovereignCuckooFilter

DEFAULT_CAPACITY = 1024


def register_cuckoo_routes(app: Any, cuckoo: Any | None = None) -> Any:
    """Register the /api/v1/cuckoo routes on ``app``; return the filter used.

    ``cuckoo`` defaults to a fresh :class:`SovereignCuckooFilter` owned by this
    app instance (factory scope — never a module-level global)."""
    if cuckoo is None:
        cuckoo = SovereignCuckooFilter(DEFAULT_CAPACITY)

    @app.post("/api/v1/cuckoo/insert")
    async def api_cuckoo_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        added = cuckoo.insert(body.get("item"))
        return JSONResponse({"inserted": added, "count": len(cuckoo)})

    @app.post("/api/v1/cuckoo/contains")
    async def api_cuckoo_contains(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        return JSONResponse({"contains": cuckoo.contains(body.get("item"))})

    @app.delete("/api/v1/cuckoo/delete")
    async def api_cuckoo_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        removed = cuckoo.delete(body.get("item"))
        return JSONResponse({"deleted": removed, "count": len(cuckoo)})

    @app.get("/api/v1/cuckoo/stats")
    async def api_cuckoo_stats() -> JSONResponse:
        return JSONResponse(cuckoo.stats())

    @app.post("/api/v1/cuckoo/reset")
    async def api_cuckoo_reset() -> JSONResponse:
        cuckoo.reset()
        return JSONResponse(cuckoo.stats())

    return cuckoo
