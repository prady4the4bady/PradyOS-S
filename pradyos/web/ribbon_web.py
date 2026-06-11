"""Phase 101 — Sovereign Ribbon Filter HTTP routes.

Exposes a :class:`~pradyos.core.ribbon.RibbonFilter` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_ribbon_routes`, called *inside* the factory — the filter lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow
another.

Like the Phase 100 XOR filter (and unlike the incremental Phase 72 Bloom / Phase
86 Cuckoo filters), the Ribbon filter is **static**: it is built once from a
complete key set by solving a GF(2) linear system, and is then immutable — so
there is no ``insert`` route, only ``build``. Keys are normalised to strings for
transport.

Routes (mounted under ``/api/v1/ribbon``):
  POST /api/v1/ribbon/build     body ``{"keys": [...]}`` — (re)build from a key set
  GET  /api/v1/ribbon/contains  ``?key=x`` — membership test (422 if not built)
  GET  /api/v1/ribbon/stats     ``{bits_per_entry, built, n, slots, ...}``
  POST /api/v1/ribbon/reset     body ``{"bits_per_entry"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.ribbon import RibbonFilter, RibbonFilterError

DEFAULT_BITS = 8


def register_ribbon_routes(app: Any, ribbon: Any | None = None) -> Any:
    """Register the /api/v1/ribbon routes on ``app``; return the filter used.

    ``ribbon`` defaults to a fresh :class:`RibbonFilter` owned by this app
    instance (factory scope — never a module-level global)."""
    if ribbon is None:
        ribbon = RibbonFilter(DEFAULT_BITS)

    @app.post("/api/v1/ribbon/build")
    async def api_ribbon_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "keys" not in body:
            return JSONResponse({"error": "keys is required"}, status_code=422)
        keys = body.get("keys")
        if not isinstance(keys, list):
            return JSONResponse({"error": "keys must be a list"}, status_code=422)
        try:
            ribbon.build([str(k) for k in keys])
        except RibbonFilterError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"built": True, "n": len(ribbon), "slots": ribbon.slots})

    @app.get("/api/v1/ribbon/contains")
    async def api_ribbon_contains(key: str) -> JSONResponse:
        try:
            contained = ribbon.contains(key)
        except RibbonFilterError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"key": key, "contained": contained})

    @app.get("/api/v1/ribbon/stats")
    async def api_ribbon_stats() -> JSONResponse:
        return JSONResponse(ribbon.stats())

    @app.post("/api/v1/ribbon/reset")
    async def api_ribbon_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            ribbon.reset(body.get("bits_per_entry"), body.get("seed"))
        except RibbonFilterError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(ribbon.stats())

    return ribbon
