"""Phase 109 — Sovereign Vacuum Filter HTTP routes.

Exposes a :class:`~pradyos.core.vacuum_filter.VacuumFilter` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_vacuum_routes`, called *inside* the factory — the filter lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

Like the Phase 86 cuckoo filter this one supports deletion (``DELETE /delete``);
unlike it, the bucket count is a multiple of the alternate range rather than a
power of two (``stats`` reports ``num_chunks`` and ``alt_range``).

Routes (mounted under ``/api/v1/vacuum``):
  POST   /api/v1/vacuum/insert    body ``{"item": any}`` — add one item
  POST   /api/v1/vacuum/contains  body ``{"item": any}`` — membership check
  DELETE /api/v1/vacuum/delete    body ``{"item": any}`` — remove one item
  GET    /api/v1/vacuum/stats     ``{capacity, num_chunks, alt_range, count, ...}``
  POST   /api/v1/vacuum/reset     clear all buckets
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.vacuum_filter import VacuumFilter

DEFAULT_CAPACITY = 1024


def register_vacuum_routes(app: Any, vacuum_filter: Any | None = None) -> Any:
    """Register the /api/v1/vacuum routes on ``app``; return the filter used.

    ``vacuum_filter`` defaults to a fresh :class:`VacuumFilter` owned by this app
    instance (factory scope — never a module-level global)."""
    if vacuum_filter is None:
        vacuum_filter = VacuumFilter(DEFAULT_CAPACITY)

    @app.post("/api/v1/vacuum/insert")
    async def api_vacuum_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        added = vacuum_filter.insert(body.get("item"))
        return JSONResponse({"inserted": added, "count": len(vacuum_filter)})

    @app.post("/api/v1/vacuum/contains")
    async def api_vacuum_contains(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        return JSONResponse({"contains": vacuum_filter.contains(body.get("item"))})

    @app.delete("/api/v1/vacuum/delete")
    async def api_vacuum_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        removed = vacuum_filter.delete(body.get("item"))
        return JSONResponse({"deleted": removed, "count": len(vacuum_filter)})

    @app.get("/api/v1/vacuum/stats")
    async def api_vacuum_stats() -> JSONResponse:
        return JSONResponse(vacuum_filter.stats())

    @app.post("/api/v1/vacuum/reset")
    async def api_vacuum_reset() -> JSONResponse:
        vacuum_filter.reset()
        return JSONResponse(vacuum_filter.stats())

    return vacuum_filter
