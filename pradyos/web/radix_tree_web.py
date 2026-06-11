"""Phase 140 — Sovereign Radix Tree HTTP routes.

Exposes a :class:`~pradyos.core.radix_tree.RadixTree` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_radixtree_routes`,
called *inside* the factory — the tree lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so
none can shadow another.

A non-string key/prefix is a request error → **HTTP 422**. ``longest_prefix`` and ``contains``
remain on the core class (not mounted).

Routes (mounted under ``/api/v1/radixtree``):
  POST   /api/v1/radixtree/insert         body ``{"key", "value"?}`` — ``{key, size}``
  POST   /api/v1/radixtree/search         body ``{"key"}`` — ``{key, found, value}``
  POST   /api/v1/radixtree/prefix_search  body ``{"prefix"}`` — ``{prefix, results, count}``
  DELETE /api/v1/radixtree/delete         body ``{"key"}`` — ``{key, deleted, size}``
  GET    /api/v1/radixtree/stats           ``{num_keys, num_nodes, compression_ratio, seed}``
  DELETE /api/v1/radixtree/reset           (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.radix_tree import RadixTree, RadixTreeError

_MISS = object()


def register_radixtree_routes(app: Any, radix_tree: Any | None = None) -> Any:
    """Register the /api/v1/radixtree routes on ``app``; return the tree used.

    ``radix_tree`` defaults to a fresh (empty) :class:`RadixTree` owned by this app instance
    (factory scope — never a module-level global)."""
    if radix_tree is None:
        radix_tree = RadixTree()

    @app.post("/api/v1/radixtree/insert")
    async def api_rx_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            radix_tree.insert(body["key"], body.get("value"))
        except RadixTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "size": len(radix_tree)})

    @app.post("/api/v1/radixtree/search")
    async def api_rx_search(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            found = radix_tree.contains(body["key"])
            value = radix_tree.search(body["key"])
        except RadixTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "found": found, "value": value})

    @app.post("/api/v1/radixtree/prefix_search")
    async def api_rx_prefix(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "prefix" not in body:
            return JSONResponse({"error": "prefix is required"}, status_code=422)
        try:
            results = radix_tree.prefix_search(body["prefix"])
        except RadixTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(
            {
                "prefix": body["prefix"],
                "results": [list(kv) for kv in results],
                "count": len(results),
            }
        )

    @app.delete("/api/v1/radixtree/delete")
    async def api_rx_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            deleted = radix_tree.delete(body["key"])
        except RadixTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "deleted": deleted, "size": len(radix_tree)})

    @app.get("/api/v1/radixtree/stats")
    async def api_rx_stats() -> JSONResponse:
        return JSONResponse(radix_tree.stats())

    @app.delete("/api/v1/radixtree/reset")
    async def api_rx_reset() -> JSONResponse:
        radix_tree.reset()
        return JSONResponse(radix_tree.stats())

    return radix_tree
