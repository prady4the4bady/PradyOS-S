"""Phase 133 — Sovereign Splay Tree HTTP routes.

Exposes a :class:`~pradyos.core.splay_tree.SplayTree` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_splaytree_routes`,
called *inside* the factory — the tree lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so
none can shadow another.

A non-orderable / wrong-kind key is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/splaytree``):
  POST   /api/v1/splaytree/insert  body ``{"key", "value"?}`` — ``{key, size, root_key}``
  POST   /api/v1/splaytree/find    body ``{"key"}`` — ``{key, found, value, root_key}``
  DELETE /api/v1/splaytree/delete  body ``{"key"}`` — ``{key, deleted, size}``
  GET    /api/v1/splaytree/stats    ``{size, height, root_key, key_kind}``
  DELETE /api/v1/splaytree/reset    (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.splay_tree import SplayTree, SplayTreeError

_MISS = object()


def register_splaytree_routes(app: Any, splay_tree: Any | None = None) -> Any:
    """Register the /api/v1/splaytree routes on ``app``; return the tree used.

    ``splay_tree`` defaults to a fresh :class:`SplayTree` owned by this app instance
    (factory scope — never a module-level global)."""
    if splay_tree is None:
        splay_tree = SplayTree()

    @app.post("/api/v1/splaytree/insert")
    async def api_st_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            splay_tree.insert(body["key"], body.get("value"))
        except SplayTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "size": len(splay_tree),
                             "root_key": splay_tree.root_key})

    @app.post("/api/v1/splaytree/find")
    async def api_st_find(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            value = splay_tree.find(body["key"], _MISS)
        except SplayTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        found = value is not _MISS
        return JSONResponse({"key": body["key"], "found": found,
                             "value": None if not found else value,
                             "root_key": splay_tree.root_key})

    @app.delete("/api/v1/splaytree/delete")
    async def api_st_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            deleted = splay_tree.delete(body["key"])
        except SplayTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "deleted": deleted, "size": len(splay_tree)})

    @app.get("/api/v1/splaytree/stats")
    async def api_st_stats() -> JSONResponse:
        return JSONResponse(splay_tree.stats())

    @app.delete("/api/v1/splaytree/reset")
    async def api_st_reset() -> JSONResponse:
        splay_tree.reset()
        return JSONResponse(splay_tree.stats())

    return splay_tree
