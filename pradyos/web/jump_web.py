"""Phase 124 — Sovereign Jump Consistent Hash HTTP routes.

Exposes a :class:`~pradyos.core.jump_hash.JumpHash` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_jump_routes`, called *inside* the factory — the (single-integer) state
lives in factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

Buckets are an ordered range ``[0, num_buckets)``; ``POST /buckets`` resizes the count
(growing moves only ≈ ``1/(N+1)`` of keys, into the new bucket).

Routes (mounted under ``/api/v1/jump``):
  GET    /api/v1/jump/assign   ``?key=`` — ``{key, bucket, num_buckets}``
  POST   /api/v1/jump/buckets  body ``{"num_buckets": int}`` — set the bucket count
  GET    /api/v1/jump/stats    ``{num_buckets, seed}``
  DELETE /api/v1/jump/reset    body ``{"num_buckets"?, "seed"?}`` — reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.jump_hash import JumpHash, JumpHashError


def register_jump_routes(app: Any, jump_hash: Any | None = None) -> Any:
    """Register the /api/v1/jump routes on ``app``; return the hasher used.

    ``jump_hash`` defaults to a fresh :class:`JumpHash` owned by this app instance
    (factory scope — never a module-level global)."""
    if jump_hash is None:
        jump_hash = JumpHash()

    @app.get("/api/v1/jump/assign")
    async def api_jump_assign(key: str) -> JSONResponse:
        return JSONResponse(
            {"key": key, "bucket": jump_hash.assign(key), "num_buckets": jump_hash.num_buckets}
        )

    @app.post("/api/v1/jump/buckets")
    async def api_jump_set_buckets(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "num_buckets" not in body:
            return JSONResponse({"error": "num_buckets is required"}, status_code=422)
        try:
            jump_hash.set_buckets(body["num_buckets"])
        except JumpHashError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"num_buckets": jump_hash.num_buckets})

    @app.get("/api/v1/jump/stats")
    async def api_jump_stats() -> JSONResponse:
        return JSONResponse(jump_hash.stats())

    @app.delete("/api/v1/jump/reset")
    async def api_jump_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            jump_hash.reset(body.get("num_buckets"), body.get("seed"))
        except JumpHashError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(jump_hash.stats())

    return jump_hash
