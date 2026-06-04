"""Phase 159 — Sovereign Scapegoat Tree HTTP routes.

Exposes a :class:`~pradyos.core.scapegoat_tree.ScapegoatTree` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_scapegoat_routes`,
called *inside* the factory — the tree lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so none
can shadow another.

A non-orderable / mixed-type key is a request error → **HTTP 422**. ``insert`` / ``delete`` carry
the key in the JSON body (preserving its type); ``contains`` takes an integer ``key`` over the
wire (the core orders any comparable keys — ints, floats, strings — as exercised by the unit
tests).

Routes (mounted under ``/api/v1/scapegoat``):
  POST   /api/v1/scapegoat/insert     body ``{"key"}`` — ``{key, added, size}``
  POST   /api/v1/scapegoat/delete     body ``{"key"}`` — ``{key, deleted, size}``
  GET    /api/v1/scapegoat/contains   query ``?key=`` — ``{key, contains}``
  GET    /api/v1/scapegoat/keys        ``{keys, size}``  (in-order)
  GET    /api/v1/scapegoat/stats       ``{size, height, alpha, min, max}``
  DELETE /api/v1/scapegoat/reset       empty the set
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.scapegoat_tree import ScapegoatTree, ScapegoatTreeError


def register_scapegoat_routes(app: Any, scapegoat_tree: Any | None = None) -> Any:
    """Register the /api/v1/scapegoat routes on ``app``; return the tree used.

    ``scapegoat_tree`` defaults to a fresh empty :class:`ScapegoatTree` (α = 2/3) owned by this app
    instance (factory scope — never a module-level global)."""
    if scapegoat_tree is None:
        scapegoat_tree = ScapegoatTree()
    sg = scapegoat_tree

    @app.post("/api/v1/scapegoat/insert")
    async def api_sg_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            added = sg.insert(body["key"])
        except ScapegoatTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "added": added, "size": sg.size})

    @app.post("/api/v1/scapegoat/delete")
    async def api_sg_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        try:
            removed = sg.delete(body["key"])
        except ScapegoatTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "deleted": removed, "size": sg.size})

    @app.get("/api/v1/scapegoat/contains")
    async def api_sg_contains(key: int = Query(...)) -> JSONResponse:
        try:
            present = sg.contains(key)
        except ScapegoatTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": key, "contains": present})

    @app.get("/api/v1/scapegoat/keys")
    async def api_sg_keys() -> JSONResponse:
        keys = sg.in_order()
        return JSONResponse({"keys": keys, "size": len(keys)})

    @app.get("/api/v1/scapegoat/stats")
    async def api_sg_stats() -> JSONResponse:
        return JSONResponse(sg.stats())

    @app.delete("/api/v1/scapegoat/reset")
    async def api_sg_reset() -> JSONResponse:
        sg.reset()
        return JSONResponse(sg.stats())

    return sg
