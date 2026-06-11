"""Phase 158 — Sovereign Leftist Heap HTTP routes.

Exposes a :class:`~pradyos.core.leftist_heap.LeftistHeap` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_leftist_routes`, called
*inside* the factory — the heap lives in factory scope (passed in, or created fresh per app), so
there is no module-level singleton. All routes are static (no path parameters), so none can shadow
another.

A non-numeric value, a malformed merge list, or a pop from an empty heap is a request error →
**HTTP 422**. ``find_min`` is a benign query: on an empty heap it returns ``{"min": null}``.

Routes (mounted under ``/api/v1/leftist``):
  POST   /api/v1/leftist/insert       body ``{"value"}`` — ``{value, size, min}``
  GET    /api/v1/leftist/find_min      ``{min, size}``  (min may be null)
  POST   /api/v1/leftist/extract_min  pop the minimum — ``{min, size}`` (422 if empty)
  POST   /api/v1/leftist/merge        body ``{"values": [...]}`` — meld a heap of ``values`` in
  GET    /api/v1/leftist/stats         ``{size, rank, min}``
  DELETE /api/v1/leftist/reset         clear the heap
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.leftist_heap import LeftistHeap, LeftistHeapError


def register_leftist_routes(app: Any, leftist_heap: Any | None = None) -> Any:
    """Register the /api/v1/leftist routes on ``app``; return the heap used.

    ``leftist_heap`` defaults to a fresh empty :class:`LeftistHeap` owned by this app instance
    (factory scope — never a module-level global)."""
    if leftist_heap is None:
        leftist_heap = LeftistHeap()
    lh = leftist_heap

    @app.post("/api/v1/leftist/insert")
    async def api_lh_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            lh.insert(body["value"])
        except LeftistHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "size": lh.size, "min": lh.stats()["min"]})

    @app.get("/api/v1/leftist/find_min")
    async def api_lh_find_min() -> JSONResponse:
        s = lh.stats()
        return JSONResponse({"min": s["min"], "size": s["size"]})

    @app.post("/api/v1/leftist/extract_min")
    async def api_lh_extract_min() -> JSONResponse:
        try:
            value = lh.extract_min()
        except LeftistHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"min": value, "size": lh.size})

    @app.post("/api/v1/leftist/merge")
    async def api_lh_merge(request: Request) -> JSONResponse:
        body = await request.json()
        values = body.get("values") if isinstance(body, dict) else None
        if not isinstance(values, list):
            return JSONResponse({"error": "values must be a list"}, status_code=422)
        other = LeftistHeap()
        try:
            for v in values:
                other.insert(v)
        except LeftistHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        lh.merge(other)
        return JSONResponse({"merged": len(values), "size": lh.size, "min": lh.stats()["min"]})

    @app.get("/api/v1/leftist/stats")
    async def api_lh_stats() -> JSONResponse:
        return JSONResponse(lh.stats())

    @app.delete("/api/v1/leftist/reset")
    async def api_lh_reset() -> JSONResponse:
        lh.reset()
        return JSONResponse(lh.stats())

    return lh
