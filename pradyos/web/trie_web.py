"""Phase 83 — Sovereign Trie HTTP routes.

Exposes a :class:`~pradyos.core.trie.SovereignTrie` over REST. The routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_trie_routes`, which is called *inside* the factory — the trie
instance lives in the factory's scope (passed in, or created fresh per app), so
there is no module-level singleton.

Routes (mounted under ``/api/v1/trie``):
  POST   /api/v1/trie                  body ``{"key": str, "value"?: any}`` — insert
  GET    /api/v1/trie/{key}            exact lookup (404 if absent)
  DELETE /api/v1/trie/{key}            remove (404 if absent)
  GET    /api/v1/trie/prefix/{prefix}  all ``(key, value)`` under a prefix
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.trie import KeyNotFoundError, SovereignTrie


def register_trie_routes(app: Any, trie: Any | None = None) -> Any:
    """Register the /api/v1/trie routes on ``app``; return the trie they use.

    ``trie`` defaults to a fresh :class:`SovereignTrie` owned by this app
    instance (factory scope — never a module-level global)."""
    if trie is None:
        trie = SovereignTrie()

    @app.post("/api/v1/trie")
    async def api_trie_insert(request: Request) -> JSONResponse:
        body = await request.json()
        key = body.get("key")
        if not isinstance(key, str) or not key:
            return JSONResponse({"error": "key must be a non-empty string"}, status_code=422)
        value = body.get("value", True)
        trie.insert(key, value)
        return JSONResponse({"key": key, "value": value, "size": len(trie)})

    @app.get("/api/v1/trie/{key}")
    async def api_trie_search(key: str) -> JSONResponse:
        try:
            value = trie.search(key)
        except KeyNotFoundError:
            return JSONResponse({"key": key, "found": False, "error": "key not found"}, status_code=404)
        return JSONResponse({"key": key, "value": value, "found": True})

    @app.delete("/api/v1/trie/{key}")
    async def api_trie_delete(key: str) -> JSONResponse:
        if not trie.delete(key):
            return JSONResponse({"key": key, "deleted": False, "error": "key not found"}, status_code=404)
        return JSONResponse({"key": key, "deleted": True, "size": len(trie)})

    @app.get("/api/v1/trie/prefix/{prefix}")
    async def api_trie_prefix(prefix: str) -> JSONResponse:
        matches = trie.starts_with(prefix)
        return JSONResponse({
            "prefix": prefix,
            "matches": [[k, v] for k, v in matches],
            "count": len(matches),
        })

    return trie
