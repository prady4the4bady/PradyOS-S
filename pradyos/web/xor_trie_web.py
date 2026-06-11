"""Phase 143 — Sovereign Binary (XOR) Trie HTTP routes.

Exposes a :class:`~pradyos.core.xor_trie.XorTrie` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_xortrie_routes`,
called *inside* the factory — the trie lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so
none can shadow another.

An out-of-range / wrong-type value, or a max/min query on an empty trie, is a request error →
**HTTP 422**. ``contains`` remains on the core class (not mounted).

Routes (mounted under ``/api/v1/xortrie``):
  POST   /api/v1/xortrie/insert          body ``{"value"}`` — ``{value, size}``
  DELETE /api/v1/xortrie/remove          body ``{"value"}`` — ``{value, removed, size}``
  POST   /api/v1/xortrie/query           body ``{"query"}`` — ``{query, max_xor, min_xor}``
  POST   /api/v1/xortrie/count_xor_less  body ``{"query", "k"}`` — ``{query, k, count}``
  GET    /api/v1/xortrie/stats            ``{size, width, num_nodes}``
  DELETE /api/v1/xortrie/reset            (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.xor_trie import XorTrie, XorTrieError


def register_xortrie_routes(app: Any, xor_trie: Any | None = None) -> Any:
    """Register the /api/v1/xortrie routes on ``app``; return the trie used.

    ``xor_trie`` defaults to a fresh (empty, 32-bit) :class:`XorTrie` owned by this app instance
    (factory scope — never a module-level global)."""
    if xor_trie is None:
        xor_trie = XorTrie()

    @app.post("/api/v1/xortrie/insert")
    async def api_xt_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            xor_trie.insert(body["value"])
        except XorTrieError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "size": len(xor_trie)})

    @app.delete("/api/v1/xortrie/remove")
    async def api_xt_remove(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            removed = xor_trie.remove(body["value"])
        except XorTrieError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "removed": removed, "size": len(xor_trie)})

    @app.post("/api/v1/xortrie/query")
    async def api_xt_query(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "query" not in body:
            return JSONResponse({"error": "query is required"}, status_code=422)
        try:
            mx = xor_trie.max_xor(body["query"])
            mn = xor_trie.min_xor(body["query"])
        except XorTrieError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"query": body["query"], "max_xor": mx, "min_xor": mn})

    @app.post("/api/v1/xortrie/count_xor_less")
    async def api_xt_count(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "query" not in body or "k" not in body:
            return JSONResponse({"error": "query and k are required"}, status_code=422)
        try:
            cnt = xor_trie.count_xor_less(body["query"], body["k"])
        except XorTrieError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"query": body["query"], "k": body["k"], "count": cnt})

    @app.get("/api/v1/xortrie/stats")
    async def api_xt_stats() -> JSONResponse:
        return JSONResponse(xor_trie.stats())

    @app.delete("/api/v1/xortrie/reset")
    async def api_xt_reset() -> JSONResponse:
        xor_trie.reset()
        return JSONResponse(xor_trie.stats())

    return xor_trie
