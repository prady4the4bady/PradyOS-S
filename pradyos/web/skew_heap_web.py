"""Phase 136 — Sovereign Skew Heap HTTP routes.

Exposes a :class:`~pradyos.core.skew_heap.SkewHeap` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_skewheap_routes`,
called *inside* the factory — the heap lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so
none can shadow another.

A non-orderable / wrong-kind value, or extracting from an empty heap, is a request error →
**HTTP 422**. ``meld`` is a two-heap operation and stays on the core class (not mounted).

Routes (mounted under ``/api/v1/skewheap``):
  POST   /api/v1/skewheap/insert       body ``{"value": ...}`` — ``{value, size, min}``
  POST   /api/v1/skewheap/extract_min  (no body) — ``{min, size}``
  GET    /api/v1/skewheap/peek          ``{min, size}`` (``min`` is null when empty)
  GET    /api/v1/skewheap/stats         ``{size, min, kind}``
  DELETE /api/v1/skewheap/reset         (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.skew_heap import SkewHeap, SkewHeapError


def register_skewheap_routes(app: Any, skew_heap: Any | None = None) -> Any:
    """Register the /api/v1/skewheap routes on ``app``; return the heap used.

    ``skew_heap`` defaults to a fresh (empty) :class:`SkewHeap` owned by this app instance
    (factory scope — never a module-level global)."""
    if skew_heap is None:
        skew_heap = SkewHeap()

    @app.post("/api/v1/skewheap/insert")
    async def api_sh_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            skew_heap.insert(body["value"])
        except SkewHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "size": len(skew_heap),
                             "min": skew_heap.peek_min()})

    @app.post("/api/v1/skewheap/extract_min")
    async def api_sh_extract() -> JSONResponse:
        try:
            value = skew_heap.extract_min()
        except SkewHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"min": value, "size": len(skew_heap)})

    @app.get("/api/v1/skewheap/peek")
    async def api_sh_peek() -> JSONResponse:
        value = None if skew_heap.is_empty() else skew_heap.peek_min()
        return JSONResponse({"min": value, "size": len(skew_heap)})

    @app.get("/api/v1/skewheap/stats")
    async def api_sh_stats() -> JSONResponse:
        return JSONResponse(skew_heap.stats())

    @app.delete("/api/v1/skewheap/reset")
    async def api_sh_reset() -> JSONResponse:
        skew_heap.reset()
        return JSONResponse(skew_heap.stats())

    return skew_heap
