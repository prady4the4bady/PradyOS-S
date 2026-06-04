"""Phase 160 — Sovereign Binomial Heap HTTP routes.

Exposes a :class:`~pradyos.core.binomial_heap.BinomialHeap` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_binomial_routes`,
called *inside* the factory — the heap lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so none
can shadow another.

A non-numeric value, a bad/dead handle, an attempt to increase a key, or a pop from an empty heap
is a request error → **HTTP 422**. ``find_min`` is a benign query: on an empty heap it returns
``{"min": null}``.

Routes (mounted under ``/api/v1/binomial``):
  POST   /api/v1/binomial/insert        body ``{"value"}`` — ``{handle, size, min}``
  GET    /api/v1/binomial/find_min       ``{min, size}``  (min may be null)
  POST   /api/v1/binomial/extract_min   pop the minimum — ``{min, size}`` (422 if empty)
  POST   /api/v1/binomial/decrease_key  body ``{"handle", "value"}`` — ``{handle, value, min, size}``
  POST   /api/v1/binomial/merge         body ``{"values": [...]}`` — meld a heap of ``values`` in
  GET    /api/v1/binomial/stats          ``{size, num_trees, min}``
  DELETE /api/v1/binomial/reset          clear the heap
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.binomial_heap import BinomialHeap, BinomialHeapError


def register_binomial_routes(app: Any, binomial_heap: Any | None = None) -> Any:
    """Register the /api/v1/binomial routes on ``app``; return the heap used.

    ``binomial_heap`` defaults to a fresh empty :class:`BinomialHeap` owned by this app instance
    (factory scope — never a module-level global)."""
    if binomial_heap is None:
        binomial_heap = BinomialHeap()
    bh = binomial_heap

    @app.post("/api/v1/binomial/insert")
    async def api_bh_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            handle = bh.insert(body["value"])
        except BinomialHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"handle": handle, "size": bh.size, "min": bh.stats()["min"]})

    @app.get("/api/v1/binomial/find_min")
    async def api_bh_find_min() -> JSONResponse:
        s = bh.stats()
        return JSONResponse({"min": s["min"], "size": s["size"]})

    @app.post("/api/v1/binomial/extract_min")
    async def api_bh_extract_min() -> JSONResponse:
        try:
            value = bh.extract_min()
        except BinomialHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"min": value, "size": bh.size})

    @app.post("/api/v1/binomial/decrease_key")
    async def api_bh_decrease_key(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "handle" not in body or "value" not in body:
            return JSONResponse({"error": "handle and value are required"}, status_code=422)
        try:
            bh.decrease_key(body["handle"], body["value"])
        except BinomialHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"handle": body["handle"], "value": body["value"],
                             "min": bh.stats()["min"], "size": bh.size})

    @app.post("/api/v1/binomial/merge")
    async def api_bh_merge(request: Request) -> JSONResponse:
        body = await request.json()
        values = body.get("values") if isinstance(body, dict) else None
        if not isinstance(values, list):
            return JSONResponse({"error": "values must be a list"}, status_code=422)
        other = BinomialHeap()
        try:
            for v in values:
                other.insert(v)
        except BinomialHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        bh.merge(other)
        return JSONResponse({"merged": len(values), "size": bh.size, "min": bh.stats()["min"]})

    @app.get("/api/v1/binomial/stats")
    async def api_bh_stats() -> JSONResponse:
        return JSONResponse(bh.stats())

    @app.delete("/api/v1/binomial/reset")
    async def api_bh_reset() -> JSONResponse:
        bh.reset()
        return JSONResponse(bh.stats())

    return bh
