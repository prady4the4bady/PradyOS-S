"""Phase 132 — Sovereign Cuckoo Hash Table HTTP routes.

Exposes a :class:`~pradyos.core.cuckoo_hashtable.CuckooHashTable` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_cuckoohash_routes`, called *inside* the factory — the table lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton. All routes
are static (no path parameters), so none can shadow another.

This is the *exact* key→value table (worst-case O(1) lookup), distinct from the Cuckoo
*Filter* of P86 at ``/api/v1/cuckoo`` (approximate set membership). A wrong-type key or bad
configuration is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/cuckoohash``):
  POST   /api/v1/cuckoohash/put     body ``{"key", "value"}`` — ``{key, size}``
  POST   /api/v1/cuckoohash/get     body ``{"key"}`` — ``{key, found, value}``
  DELETE /api/v1/cuckoohash/remove  body ``{"key"}`` — ``{key, removed}``
  GET    /api/v1/cuckoohash/stats    ``{size, capacity, total_slots, load_factor, num_rehashes, seed}``
  DELETE /api/v1/cuckoohash/reset    body ``{"capacity"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.cuckoo_hashtable import CuckooHashTable, CuckooHashError

_MISS = object()


def register_cuckoohash_routes(app: Any, cuckoo_hashtable: Any | None = None) -> Any:
    """Register the /api/v1/cuckoohash routes on ``app``; return the table used.

    ``cuckoo_hashtable`` defaults to a fresh :class:`CuckooHashTable` owned by this app
    instance (factory scope — never a module-level global)."""
    if cuckoo_hashtable is None:
        cuckoo_hashtable = CuckooHashTable()

    @app.post("/api/v1/cuckoohash/put")
    async def api_ch_put(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body or "value" not in body:
            return JSONResponse({"error": "key and value are required"}, status_code=422)
        try:
            cuckoo_hashtable.put(body["key"], body["value"])
        except CuckooHashError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "size": len(cuckoo_hashtable)})

    @app.post("/api/v1/cuckoohash/get")
    async def api_ch_get(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            value = cuckoo_hashtable.get(body["key"], _MISS)
        except CuckooHashError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        found = value is not _MISS
        return JSONResponse({"key": body["key"], "found": found,
                             "value": None if not found else value})

    @app.delete("/api/v1/cuckoohash/remove")
    async def api_ch_remove(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            removed = cuckoo_hashtable.remove(body["key"])
        except CuckooHashError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "removed": removed})

    @app.get("/api/v1/cuckoohash/stats")
    async def api_ch_stats() -> JSONResponse:
        return JSONResponse(cuckoo_hashtable.stats())

    @app.delete("/api/v1/cuckoohash/reset")
    async def api_ch_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            cuckoo_hashtable.reset(body.get("capacity"), body.get("seed"))
        except CuckooHashError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(cuckoo_hashtable.stats())

    return cuckoo_hashtable
