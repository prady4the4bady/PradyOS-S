"""Phase 100 — Sovereign XOR Filter HTTP routes.  🎯 centennial.

Exposes an :class:`~pradyos.core.xor_filter.XorFilter` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_xor_filter_routes`, called *inside* the factory — the filter lives
in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Unlike the Phase 72 Bloom and Phase 86 Cuckoo filters (incremental), the XOR
filter is **static**: it is built once from a complete key set and is then
immutable — so there is no ``insert`` route, only ``build``. Keys are normalised
to strings for transport.

Routes (mounted under ``/api/v1/xorfilter``):
  POST /api/v1/xorfilter/build     body ``{"keys": [...]}`` — (re)build from a key set
  GET  /api/v1/xorfilter/contains  ``?key=x`` — membership test (422 if not built)
  GET  /api/v1/xorfilter/stats     ``{bits_per_entry, built, n, array_size, ...}``
  POST /api/v1/xorfilter/reset     body ``{"bits_per_entry"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.xor_filter import XorFilter, XorFilterError

DEFAULT_BITS = 8


def register_xor_filter_routes(app: Any, xor: Any | None = None) -> Any:
    """Register the /api/v1/xorfilter routes on ``app``; return the filter used.

    ``xor`` defaults to a fresh :class:`XorFilter` owned by this app instance
    (factory scope — never a module-level global)."""
    if xor is None:
        xor = XorFilter(DEFAULT_BITS)

    @app.post("/api/v1/xorfilter/build")
    async def api_xor_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "keys" not in body:
            return JSONResponse({"error": "keys is required"}, status_code=422)
        keys = body.get("keys")
        if not isinstance(keys, list):
            return JSONResponse({"error": "keys must be a list"}, status_code=422)
        try:
            xor.build([str(k) for k in keys])
        except XorFilterError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"built": True, "n": len(xor), "array_size": xor.array_size})

    @app.get("/api/v1/xorfilter/contains")
    async def api_xor_contains(key: str) -> JSONResponse:
        try:
            contained = xor.contains(key)
        except XorFilterError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"key": key, "contained": contained})

    @app.get("/api/v1/xorfilter/stats")
    async def api_xor_stats() -> JSONResponse:
        return JSONResponse(xor.stats())

    @app.post("/api/v1/xorfilter/reset")
    async def api_xor_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            xor.reset(body.get("bits_per_entry"), body.get("seed"))
        except XorFilterError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(xor.stats())

    return xor
