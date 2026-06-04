"""Phase 155 — Sovereign AVL Tree HTTP routes.

Exposes an :class:`~pradyos.core.avl_tree.AVLTree` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_avl_routes`, called
*inside* the factory — the tree lives in factory scope (passed in, or created fresh per app), so
there is no module-level singleton. All routes are static (no path parameters), so none can shadow
another.

A non-orderable / mixed-type key is a request error → **HTTP 422**. ``successor`` /
``predecessor`` return ``null`` when there is no such key. The read queries take an integer
``key`` over the wire (the core itself orders any comparable keys — ints, floats, strings — as
exercised by the unit tests); ``insert`` / ``delete`` carry the key in the JSON body, preserving
its type.

Routes (mounted under ``/api/v1/avl``):
  POST   /api/v1/avl/insert       body ``{"key"}`` — ``{key, added, size}``
  POST   /api/v1/avl/delete       body ``{"key"}`` — ``{key, deleted, size}``
  GET    /api/v1/avl/contains     query ``?key=`` — ``{key, contains}``
  GET    /api/v1/avl/successor    query ``?key=`` — ``{key, successor}``  (may be null)
  GET    /api/v1/avl/predecessor  query ``?key=`` — ``{key, predecessor}``  (may be null)
  GET    /api/v1/avl/stats         ``{size, height, min, max}``
  DELETE /api/v1/avl/reset         empty the set
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.avl_tree import AVLTree, AVLTreeError


def register_avl_routes(app: Any, avl_tree: Any | None = None) -> Any:
    """Register the /api/v1/avl routes on ``app``; return the tree used.

    ``avl_tree`` defaults to a fresh empty :class:`AVLTree` owned by this app instance
    (factory scope — never a module-level global)."""
    if avl_tree is None:
        avl_tree = AVLTree()
    avl = avl_tree

    @app.post("/api/v1/avl/insert")
    async def api_avl_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            added = avl.insert(body["key"])
        except AVLTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "added": added, "size": avl.size})

    @app.post("/api/v1/avl/delete")
    async def api_avl_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            removed = avl.delete(body["key"])
        except AVLTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "deleted": removed, "size": avl.size})

    @app.get("/api/v1/avl/contains")
    async def api_avl_contains(key: int = Query(...)) -> JSONResponse:
        try:
            present = avl.contains(key)
        except AVLTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": key, "contains": present})

    @app.get("/api/v1/avl/successor")
    async def api_avl_successor(key: int = Query(...)) -> JSONResponse:
        try:
            s = avl.successor(key)
        except AVLTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": key, "successor": s})

    @app.get("/api/v1/avl/predecessor")
    async def api_avl_predecessor(key: int = Query(...)) -> JSONResponse:
        try:
            p = avl.predecessor(key)
        except AVLTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": key, "predecessor": p})

    @app.get("/api/v1/avl/stats")
    async def api_avl_stats() -> JSONResponse:
        return JSONResponse(avl.stats())

    @app.delete("/api/v1/avl/reset")
    async def api_avl_reset() -> JSONResponse:
        avl.reset()
        return JSONResponse(avl.stats())

    return avl
