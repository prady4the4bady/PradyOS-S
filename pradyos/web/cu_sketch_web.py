"""Phase 123 — Sovereign CU-Sketch (Conservative-Update Count-Min) HTTP routes.

Exposes a :class:`~pradyos.core.cu_sketch.CUSketch` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_cusketch_routes`, called *inside* the factory — the sketch lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton. All
routes are static (no path parameters), so none can shadow another.

There is **no remove** route — conservative update cannot be safely reversed, so the
sketch is insert-and-query.

Routes (mounted under ``/api/v1/cusketch``):
  POST   /api/v1/cusketch/add       body ``{"item": x, "amount"?: int}`` — add occurrences
  GET    /api/v1/cusketch/estimate  ``?item=`` — estimated frequency
  GET    /api/v1/cusketch/stats     ``{width, depth, total, num_counters, seed}``
  DELETE /api/v1/cusketch/reset     body ``{"width"?, "depth"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.cu_sketch import CUSketch, CUSketchError


def register_cusketch_routes(app: Any, cu_sketch: Any | None = None) -> Any:
    """Register the /api/v1/cusketch routes on ``app``; return the sketch used.

    ``cu_sketch`` defaults to a fresh :class:`CUSketch` owned by this app instance
    (factory scope — never a module-level global)."""
    if cu_sketch is None:
        cu_sketch = CUSketch()

    @app.post("/api/v1/cusketch/add")
    async def api_cu_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        item = str(body["item"])
        try:
            cu_sketch.add(item, body.get("amount", 1))
        except CUSketchError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"item": item, "estimate": cu_sketch.estimate(item),
                            "total": cu_sketch.total})

    @app.get("/api/v1/cusketch/estimate")
    async def api_cu_estimate(item: str) -> JSONResponse:
        return JSONResponse({"item": item, "estimate": cu_sketch.estimate(item)})

    @app.get("/api/v1/cusketch/stats")
    async def api_cu_stats() -> JSONResponse:
        return JSONResponse(cu_sketch.stats())

    @app.delete("/api/v1/cusketch/reset")
    async def api_cu_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            cu_sketch.reset(body.get("width"), body.get("depth"), body.get("seed"))
        except CUSketchError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(cu_sketch.stats())

    return cu_sketch
