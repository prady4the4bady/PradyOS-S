"""Phase 154 — Sovereign Fibonacci Heap HTTP routes.

Exposes a :class:`~pradyos.core.fibonacci_heap.FibonacciHeap` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_fibonacci_routes`,
called *inside* the factory — the heap lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so none
can shadow another.

A non-numeric value, a bad/dead handle, an attempt to increase a key, or a pop from an empty heap
is a request error → **HTTP 422**. ``find_min`` is a benign query: on an empty heap it returns
``{"min": null, "size": 0}`` rather than erroring.

Routes (mounted under ``/api/v1/fibonacci``):
  POST   /api/v1/fibonacci/insert        body ``{"value"}`` — ``{handle, size, min}``
  GET    /api/v1/fibonacci/find_min       ``{min, size}``  (min may be null)
  POST   /api/v1/fibonacci/extract_min   pop the minimum — ``{min, size}`` (422 if empty)
  POST   /api/v1/fibonacci/decrease_key  body ``{"handle", "value"}`` — ``{handle, value, min, size}``
  GET    /api/v1/fibonacci/stats          ``{size, num_trees, min}``
  DELETE /api/v1/fibonacci/reset          clear the heap
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.fibonacci_heap import FibonacciHeap, FibonacciHeapError


def register_fibonacci_routes(app: Any, fibonacci_heap: Any | None = None) -> Any:
    """Register the /api/v1/fibonacci routes on ``app``; return the heap used.

    ``fibonacci_heap`` defaults to a fresh empty :class:`FibonacciHeap` owned by this app instance
    (factory scope — never a module-level global)."""
    if fibonacci_heap is None:
        fibonacci_heap = FibonacciHeap()
    fh = fibonacci_heap

    @app.post("/api/v1/fibonacci/insert")
    async def api_fib_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            handle = fh.insert(body["value"])
        except FibonacciHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"handle": handle, "size": fh.size, "min": fh.stats()["min"]})

    @app.get("/api/v1/fibonacci/find_min")
    async def api_fib_find_min() -> JSONResponse:
        s = fh.stats()
        return JSONResponse({"min": s["min"], "size": s["size"]})

    @app.post("/api/v1/fibonacci/extract_min")
    async def api_fib_extract_min() -> JSONResponse:
        try:
            value = fh.extract_min()
        except FibonacciHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"min": value, "size": fh.size})

    @app.post("/api/v1/fibonacci/decrease_key")
    async def api_fib_decrease_key(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "handle" not in body or "value" not in body:
            return JSONResponse({"error": "handle and value are required"}, status_code=422)
        try:
            fh.decrease_key(body["handle"], body["value"])
        except FibonacciHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"handle": body["handle"], "value": body["value"],
                             "min": fh.stats()["min"], "size": fh.size})

    @app.get("/api/v1/fibonacci/stats")
    async def api_fib_stats() -> JSONResponse:
        return JSONResponse(fh.stats())

    @app.delete("/api/v1/fibonacci/reset")
    async def api_fib_reset() -> JSONResponse:
        fh.reset()
        return JSONResponse(fh.stats())

    return fh
