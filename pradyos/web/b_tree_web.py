"""Phase 156 — Sovereign B-Tree HTTP routes.

Exposes a :class:`~pradyos.core.b_tree.BTree` over REST. Routes are registered onto the FastAPI
``app`` built by ``sovereign_web.create_app()`` via :func:`register_btree_routes`, called *inside*
the factory — the tree lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can shadow another.

A non-orderable / mixed-type key is a request error → **HTTP 422**. ``insert`` / ``delete`` carry
the key in the JSON body (preserving its type); ``contains`` takes an integer ``key`` over the
wire (the core orders any comparable keys — ints, floats, strings — as exercised by the unit
tests).

Routes (mounted under ``/api/v1/btree``):
  POST   /api/v1/btree/insert     body ``{"key"}`` — ``{key, added, size}``
  POST   /api/v1/btree/delete     body ``{"key"}`` — ``{key, deleted, size}``
  GET    /api/v1/btree/contains   query ``?key=`` — ``{key, contains}``
  GET    /api/v1/btree/keys        ``{keys, size}``  (in-order)
  GET    /api/v1/btree/stats       ``{size, height, min_degree, min, max}``
  DELETE /api/v1/btree/reset       empty the set
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.b_tree import BTree, BTreeError


def register_btree_routes(app: Any, b_tree: Any | None = None) -> Any:
    """Register the /api/v1/btree routes on ``app``; return the tree used.

    ``b_tree`` defaults to a fresh empty :class:`BTree` (min degree 3) owned by this app instance
    (factory scope — never a module-level global)."""
    if b_tree is None:
        b_tree = BTree()
    bt = b_tree

    @app.post("/api/v1/btree/insert")
    async def api_btree_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            added = bt.insert(body["key"])
        except BTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "added": added, "size": bt.size})

    @app.post("/api/v1/btree/delete")
    async def api_btree_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            removed = bt.delete(body["key"])
        except BTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "deleted": removed, "size": bt.size})

    @app.get("/api/v1/btree/contains")
    async def api_btree_contains(key: int = Query(...)) -> JSONResponse:
        try:
            present = bt.contains(key)
        except BTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": key, "contains": present})

    @app.get("/api/v1/btree/keys")
    async def api_btree_keys() -> JSONResponse:
        keys = bt.in_order()
        return JSONResponse({"keys": keys, "size": len(keys)})

    @app.get("/api/v1/btree/stats")
    async def api_btree_stats() -> JSONResponse:
        return JSONResponse(bt.stats())

    @app.delete("/api/v1/btree/reset")
    async def api_btree_reset() -> JSONResponse:
        bt.reset()
        return JSONResponse(bt.stats())

    return bt
