"""Phase 108 — Sovereign Binary Fuse Filter HTTP routes.

Exposes a :class:`~pradyos.core.binary_fuse.BinaryFuseFilter` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()``
via :func:`register_binaryfuse_routes`, called *inside* the factory — the filter
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

The filter is **static**: there is no incremental ``add`` — it is constructed in
one shot from a complete key set via ``build``, queried with ``contains``, and
cleared with ``reset``. ``BinaryFuseError`` conditions (not-built / duplicate
keys / build cycle) surface as **HTTP 400** (a state error), distinct from the
422 used for request-shape validation.

Routes (mounted under ``/api/v1/binaryfuse``):
  POST   /api/v1/binaryfuse/build     body ``{"keys": ["...", ...]}`` — build (or rebuild); 400 on duplicate / cycle
  GET    /api/v1/binaryfuse/contains  ``?key=`` — membership test; 400 before build
  GET    /api/v1/binaryfuse/stats     ``{built, num_keys, array_size, bits_per_key, seed}``
  DELETE /api/v1/binaryfuse/reset     body ``{"seed"?}`` — clear back to unbuilt / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.binary_fuse import BinaryFuseError, BinaryFuseFilter


def register_binaryfuse_routes(app: Any, binary_fuse: Any | None = None) -> Any:
    """Register the /api/v1/binaryfuse routes on ``app``; return the filter used.

    ``binary_fuse`` defaults to a fresh (unbuilt) :class:`BinaryFuseFilter` owned
    by this app instance (factory scope — never a module-level global)."""
    if binary_fuse is None:
        binary_fuse = BinaryFuseFilter()

    @app.post("/api/v1/binaryfuse/build")
    async def api_bf_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("keys"), list):
            return JSONResponse({"error": "keys list is required"}, status_code=422)
        try:
            binary_fuse.build([str(k) for k in body["keys"]])
        except BinaryFuseError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse(binary_fuse.stats())

    @app.get("/api/v1/binaryfuse/contains")
    async def api_bf_contains(key: str) -> JSONResponse:
        try:
            present = binary_fuse.contains(key)
        except BinaryFuseError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"key": key, "contains": present})

    @app.get("/api/v1/binaryfuse/stats")
    async def api_bf_stats() -> JSONResponse:
        return JSONResponse(binary_fuse.stats())

    @app.delete("/api/v1/binaryfuse/reset")
    async def api_bf_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            binary_fuse.reset(body.get("seed"))
        except BinaryFuseError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(binary_fuse.stats())

    return binary_fuse
