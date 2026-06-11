"""Phase 84 — Sovereign LRU Cache HTTP routes.

Exposes a :class:`~pradyos.core.lru_cache.SovereignLRUCache` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_lru_routes`, which is called *inside* the factory — the cache
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton.

Routes (mounted under ``/api/v1/lru``):
  GET    /api/v1/lru/snapshot   full cache state, most-recently-used first
  POST   /api/v1/lru/resize     body ``{"capacity": int}`` — change capacity live
  PUT    /api/v1/lru/{key}      body ``{"value"?: any, "ttl"?: number}`` — insert/update
  GET    /api/v1/lru/{key}      fetch (404 on miss, 422 on bad input)
  DELETE /api/v1/lru/{key}      evict (404 if absent)

The static ``/snapshot`` and ``/resize`` routes are declared before the
``/{key}`` routes so the path parameter never shadows them.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.lru_cache import CacheMissError, SovereignLRUCache

DEFAULT_CAPACITY = 128


def register_lru_routes(app: Any, cache: Any | None = None) -> Any:
    """Register the /api/v1/lru routes on ``app``; return the cache they use.

    ``cache`` defaults to a fresh :class:`SovereignLRUCache` owned by this app
    instance (factory scope — never a module-level global)."""
    if cache is None:
        cache = SovereignLRUCache(DEFAULT_CAPACITY)

    # ── static routes first (so /{key} cannot shadow them) ───────────────────
    @app.get("/api/v1/lru/snapshot")
    async def api_lru_snapshot() -> JSONResponse:
        return JSONResponse(cache.to_dict())

    @app.post("/api/v1/lru/resize")
    async def api_lru_resize(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            cache.resize(body.get("capacity"))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"capacity": cache.capacity, "size": len(cache)})

    # ── key-scoped routes ─────────────────────────────────────────────────────
    @app.put("/api/v1/lru/{key}")
    async def api_lru_put(key: str, request: Request) -> JSONResponse:
        body = await request.json()
        value = body.get("value", True)
        ttl = body.get("ttl")
        try:
            cache.put(key, value, ttl)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"key": key, "value": value, "ttl": ttl, "size": len(cache)})

    @app.get("/api/v1/lru/{key}")
    async def api_lru_get(key: str) -> JSONResponse:
        try:
            value = cache.get(key)
        except CacheMissError:
            return JSONResponse(
                {"key": key, "found": False, "error": "cache miss"}, status_code=404
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"key": key, "value": value, "found": True})

    @app.delete("/api/v1/lru/{key}")
    async def api_lru_delete(key: str) -> JSONResponse:
        if not cache.delete(key):
            return JSONResponse(
                {"key": key, "deleted": False, "error": "cache miss"}, status_code=404
            )
        return JSONResponse({"key": key, "deleted": True, "size": len(cache)})

    return cache
