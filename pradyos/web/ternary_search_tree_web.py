"""Phase 164 — Sovereign Ternary Search Tree HTTP routes.

Exposes a :class:`~pradyos.core.ternary_search_tree.TernarySearchTree` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_tst_routes`, called *inside* the factory — the table lives in factory scope
(passed in, or created fresh per app), so there is no module-level singleton. All routes are static
(no path parameters), so none can shadow another.

A non-string key, or an empty key on ``insert``, is a request error → **HTTP 422**.
``longest_prefix_of`` returns ``null`` when no stored key is a prefix of the query.

Routes (mounted under ``/api/v1/tst``):
  POST   /api/v1/tst/insert            body ``{"key"}`` — ``{key, added, size}``
  POST   /api/v1/tst/delete            body ``{"key"}`` — ``{key, deleted, size}``
  GET    /api/v1/tst/contains          query ``?key=`` — ``{key, contains}``
  GET    /api/v1/tst/keys_with_prefix  query ``?prefix=`` — ``{prefix, keys, count}``
  GET    /api/v1/tst/longest_prefix_of query ``?query=`` — ``{query, longest_prefix}``  (may be null)
  GET    /api/v1/tst/keys               ``{keys, size}``
  GET    /api/v1/tst/stats              ``{size, nodes}``
  DELETE /api/v1/tst/reset              empty the table
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.ternary_search_tree import TernarySearchTree, TernarySearchTreeError


def register_tst_routes(app: Any, ternary_search_tree: Any | None = None) -> Any:
    """Register the /api/v1/tst routes on ``app``; return the table used.

    ``ternary_search_tree`` defaults to a fresh empty :class:`TernarySearchTree` owned by this app
    instance (factory scope — never a module-level global)."""
    if ternary_search_tree is None:
        ternary_search_tree = TernarySearchTree()
    tst = ternary_search_tree

    @app.post("/api/v1/tst/insert")
    async def api_tst_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            added = tst.insert(body["key"])
        except TernarySearchTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "added": added, "size": tst.size})

    @app.post("/api/v1/tst/delete")
    async def api_tst_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            removed = tst.delete(body["key"])
        except TernarySearchTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "deleted": removed, "size": tst.size})

    @app.get("/api/v1/tst/contains")
    async def api_tst_contains(key: str = Query(...)) -> JSONResponse:
        try:
            present = tst.contains(key)
        except TernarySearchTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": key, "contains": present})

    @app.get("/api/v1/tst/keys_with_prefix")
    async def api_tst_prefix(prefix: str = Query("")) -> JSONResponse:
        try:
            keys = tst.keys_with_prefix(prefix)
        except TernarySearchTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"prefix": prefix, "keys": keys, "count": len(keys)})

    @app.get("/api/v1/tst/longest_prefix_of")
    async def api_tst_longest(query: str = Query("")) -> JSONResponse:
        try:
            lp = tst.longest_prefix_of(query)
        except TernarySearchTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"query": query, "longest_prefix": lp})

    @app.get("/api/v1/tst/keys")
    async def api_tst_keys() -> JSONResponse:
        keys = tst.keys()
        return JSONResponse({"keys": keys, "size": len(keys)})

    @app.get("/api/v1/tst/stats")
    async def api_tst_stats() -> JSONResponse:
        return JSONResponse(tst.stats())

    @app.delete("/api/v1/tst/reset")
    async def api_tst_reset() -> JSONResponse:
        tst.reset()
        return JSONResponse(tst.stats())

    return tst
