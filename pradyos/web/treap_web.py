"""Phase 113 — Sovereign Treap HTTP routes.

Exposes a :class:`~pradyos.core.treap.Treap` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_treap_routes`, called *inside* the factory — the tree lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton.

Keys are **numeric** (int/float) so the order-statistics routes (``rank`` /
``select``) have a meaningful total order; values may be any JSON. ``select`` with
an in-range-syntax-but-out-of-bounds index surfaces as **HTTP 400** (a state error,
distinct from the 422 used for request-shape validation).

Routes (mounted under ``/api/v1/treap``):
  POST   /api/v1/treap/insert  body ``{"key": number, "value"?: any}`` — insert / update
  DELETE /api/v1/treap/delete  body ``{"key": number}`` — remove a key
  GET    /api/v1/treap/search  ``?key=`` — ``{key, found, value}``
  GET    /api/v1/treap/rank    ``?key=`` — keys strictly less than ``key``
  GET    /api/v1/treap/select  ``?index=`` — the ``index``-th smallest key; 400 if out of range
  GET    /api/v1/treap/stats   ``{size, height, min, max, seed}``
  DELETE /api/v1/treap/reset   body ``{"seed"?}`` — empty / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.treap import Treap, TreapError


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def register_treap_routes(app: Any, treap: Any | None = None) -> Any:
    """Register the /api/v1/treap routes on ``app``; return the tree used.

    ``treap`` defaults to a fresh :class:`Treap` owned by this app instance
    (factory scope — never a module-level global)."""
    if treap is None:
        treap = Treap()

    @app.post("/api/v1/treap/insert")
    async def api_treap_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not _is_number(body.get("key")):
            return JSONResponse({"error": "numeric key is required"}, status_code=422)
        treap.insert(body["key"], body.get("value"))
        return JSONResponse({"key": body["key"], "size": len(treap)})

    @app.delete("/api/v1/treap/delete")
    async def api_treap_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not _is_number(body.get("key")):
            return JSONResponse({"error": "numeric key is required"}, status_code=422)
        removed = treap.delete(body["key"])
        return JSONResponse({"key": body["key"], "deleted": removed, "size": len(treap)})

    @app.get("/api/v1/treap/search")
    async def api_treap_search(key: float) -> JSONResponse:
        found = treap.contains(key)
        return JSONResponse(
            {"key": key, "found": found, "value": treap.get(key) if found else None}
        )

    @app.get("/api/v1/treap/rank")
    async def api_treap_rank(key: float) -> JSONResponse:
        return JSONResponse({"key": key, "rank": treap.rank(key)})

    @app.get("/api/v1/treap/select")
    async def api_treap_select(index: int = Query(ge=0)) -> JSONResponse:
        try:
            k = treap.select(index)
        except TreapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"index": index, "key": k})

    @app.get("/api/v1/treap/stats")
    async def api_treap_stats() -> JSONResponse:
        return JSONResponse(treap.stats())

    @app.delete("/api/v1/treap/reset")
    async def api_treap_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            treap.reset(body.get("seed"))
        except TreapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(treap.stats())

    return treap
