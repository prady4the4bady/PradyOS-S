"""Phase 90 — Sovereign Quotient Filter HTTP routes.

Exposes a :class:`~pradyos.core.quotient.QuotientFilter` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_quotient_routes`, called *inside* the factory — the filter lives
in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Like the Phase 86 Cuckoo filter it supports deletion, and additionally **counts
duplicates** natively (the count is returned on insert/contains/delete).

Routes (mounted under ``/api/v1/quotient``):
  POST   /api/v1/quotient/insert    body ``{"item": any}`` — add one occurrence
  POST   /api/v1/quotient/contains  body ``{"item": any}`` — membership + count
  DELETE /api/v1/quotient/delete    body ``{"item": any}`` — remove one occurrence
  GET    /api/v1/quotient/stats     ``{q, slots, remainder_bits, used, items, ...}``
  POST   /api/v1/quotient/reset     body ``{"q"?, "r"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.quotient import QuotientError, QuotientFilter

DEFAULT_Q = 10        # 1024 slots — a sensible per-app default


def register_quotient_routes(app: Any, quotient: Any | None = None) -> Any:
    """Register the /api/v1/quotient routes on ``app``; return the filter used.

    ``quotient`` defaults to a fresh :class:`QuotientFilter` owned by this app
    instance (factory scope — never a module-level global)."""
    if quotient is None:
        quotient = QuotientFilter(DEFAULT_Q)

    @app.post("/api/v1/quotient/insert")
    async def api_quotient_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        added = quotient.insert(body.get("item"))
        return JSONResponse({"inserted": added, "count": quotient.count(body.get("item")),
                             "used": len(quotient)})

    @app.post("/api/v1/quotient/contains")
    async def api_quotient_contains(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        return JSONResponse({"contains": quotient.contains(body.get("item")),
                             "count": quotient.count(body.get("item"))})

    @app.delete("/api/v1/quotient/delete")
    async def api_quotient_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        removed = quotient.delete(body.get("item"))
        return JSONResponse({"deleted": removed, "count": quotient.count(body.get("item")),
                             "used": len(quotient)})

    @app.get("/api/v1/quotient/stats")
    async def api_quotient_stats() -> JSONResponse:
        return JSONResponse(quotient.stats())

    @app.post("/api/v1/quotient/reset")
    async def api_quotient_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            quotient.reset(body.get("q"), body.get("r"), body.get("seed"))
        except QuotientError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(quotient.stats())

    return quotient
