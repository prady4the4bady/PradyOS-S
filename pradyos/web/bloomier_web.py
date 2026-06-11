"""Phase 114 — Sovereign Bloomier Filter HTTP routes.

Exposes a :class:`~pradyos.core.bloomier.BloomierFilter` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_bloomier_routes`, called *inside* the factory — the filter lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

The filter is **static**: it is constructed in one shot from a complete ``mapping``
via ``build`` (keys are the JSON object's string keys; values may be any JSON), then
queried with ``get``, and cleared with ``reset``. ``BloomierError`` conditions
(not-built / build cycle / duplicate keys) surface as **HTTP 400** (a state error),
distinct from the 422 used for request-shape validation. ``found`` reflects the
fingerprint membership check (exact for members; a ``2^(−fingerprint_bits)`` false
positive for non-members).

Routes (mounted under ``/api/v1/bloomier``):
  POST   /api/v1/bloomier/build  body ``{"mapping": {"k": v, ...}}`` — build (or rebuild); 400 on cycle/dup
  GET    /api/v1/bloomier/get    ``?key=`` — ``{key, found, value}``; 400 before build
  GET    /api/v1/bloomier/stats  ``{built, num_keys, num_cells, fingerprint_bits, value_bits, bits_per_key, seed}``
  DELETE /api/v1/bloomier/reset  body ``{"seed"?}`` — clear back to unbuilt / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.bloomier import BloomierError, BloomierFilter


def register_bloomier_routes(app: Any, bloomier: Any | None = None) -> Any:
    """Register the /api/v1/bloomier routes on ``app``; return the filter used.

    ``bloomier`` defaults to a fresh (unbuilt) :class:`BloomierFilter` owned by this
    app instance (factory scope — never a module-level global)."""
    if bloomier is None:
        bloomier = BloomierFilter()

    @app.post("/api/v1/bloomier/build")
    async def api_bloomier_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("mapping"), dict):
            return JSONResponse({"error": "mapping object is required"}, status_code=422)
        try:
            bloomier.build(body["mapping"])
        except BloomierError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse(bloomier.stats())

    @app.get("/api/v1/bloomier/get")
    async def api_bloomier_get(key: str) -> JSONResponse:
        try:
            found = bloomier.contains(key)
            value = bloomier.get(key) if found else None
        except BloomierError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"key": key, "found": found, "value": value})

    @app.get("/api/v1/bloomier/stats")
    async def api_bloomier_stats() -> JSONResponse:
        return JSONResponse(bloomier.stats())

    @app.delete("/api/v1/bloomier/reset")
    async def api_bloomier_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            bloomier.reset(body.get("seed"))
        except BloomierError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(bloomier.stats())

    return bloomier
