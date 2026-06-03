"""Phase 144 — Sovereign Min-Max Heap HTTP routes.

Exposes a :class:`~pradyos.core.min_max_heap.MinMaxHeap` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_minmaxheap_routes`, called *inside* the factory — the heap lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton. All routes
are static (no path parameters), so none can shadow another.

A non-orderable / wrong-kind value, or extracting from an empty heap, is a request error →
**HTTP 422**.

Routes (mounted under ``/api/v1/minmaxheap``):
  POST   /api/v1/minmaxheap/push         body ``{"value"}`` — ``{value, size, min, max}``
  POST   /api/v1/minmaxheap/extract_min  (no body) — ``{min, size}``
  POST   /api/v1/minmaxheap/extract_max  (no body) — ``{max, size}``
  GET    /api/v1/minmaxheap/peek          ``{min, max, size}`` (``min``/``max`` null when empty)
  GET    /api/v1/minmaxheap/stats          ``{size, min, max, kind}``
  DELETE /api/v1/minmaxheap/reset          (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.min_max_heap import MinMaxHeap, MinMaxHeapError


def register_minmaxheap_routes(app: Any, min_max_heap: Any | None = None) -> Any:
    """Register the /api/v1/minmaxheap routes on ``app``; return the heap used.

    ``min_max_heap`` defaults to a fresh (empty) :class:`MinMaxHeap` owned by this app instance
    (factory scope — never a module-level global)."""
    if min_max_heap is None:
        min_max_heap = MinMaxHeap()

    @app.post("/api/v1/minmaxheap/push")
    async def api_mmh_push(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            min_max_heap.push(body["value"])
        except MinMaxHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "size": len(min_max_heap),
                             "min": min_max_heap.peek_min(), "max": min_max_heap.peek_max()})

    @app.post("/api/v1/minmaxheap/extract_min")
    async def api_mmh_extract_min() -> JSONResponse:
        try:
            value = min_max_heap.extract_min()
        except MinMaxHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"min": value, "size": len(min_max_heap)})

    @app.post("/api/v1/minmaxheap/extract_max")
    async def api_mmh_extract_max() -> JSONResponse:
        try:
            value = min_max_heap.extract_max()
        except MinMaxHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"max": value, "size": len(min_max_heap)})

    @app.get("/api/v1/minmaxheap/peek")
    async def api_mmh_peek() -> JSONResponse:
        if min_max_heap.is_empty():
            return JSONResponse({"min": None, "max": None, "size": 0})
        return JSONResponse({"min": min_max_heap.peek_min(), "max": min_max_heap.peek_max(),
                             "size": len(min_max_heap)})

    @app.get("/api/v1/minmaxheap/stats")
    async def api_mmh_stats() -> JSONResponse:
        return JSONResponse(min_max_heap.stats())

    @app.delete("/api/v1/minmaxheap/reset")
    async def api_mmh_reset() -> JSONResponse:
        min_max_heap.reset()
        return JSONResponse(min_max_heap.stats())

    return min_max_heap
