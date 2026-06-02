"""Phase 118 — Sovereign Scalable Bloom Filter HTTP routes.

Exposes a :class:`~pradyos.core.scalable_bloom.ScalableBloomFilter` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_scalablebloom_routes`, called *inside* the factory — the filter lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

The filter **grows on its own** — there is no capacity to manage; ``add`` appends new,
tighter layers as needed while keeping the compounded false-positive rate bounded.

Routes (mounted under ``/api/v1/scalablebloom``):
  POST   /api/v1/scalablebloom/add       body ``{"element": x}`` — add an element
  GET    /api/v1/scalablebloom/contains  ``?element=`` — membership test
  GET    /api/v1/scalablebloom/stats     ``{count, num_layers, initial_capacity, error_rate, ratio, growth, total_bits, false_positive_rate, seed}``
  DELETE /api/v1/scalablebloom/reset     body ``{"initial_capacity"?, "error_rate"?, "ratio"?, "growth"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.scalable_bloom import ScalableBloomFilter, ScalableBloomError


def register_scalablebloom_routes(app: Any, scalable_bloom: Any | None = None) -> Any:
    """Register the /api/v1/scalablebloom routes on ``app``; return the filter used.

    ``scalable_bloom`` defaults to a fresh :class:`ScalableBloomFilter` owned by this
    app instance (factory scope — never a module-level global)."""
    if scalable_bloom is None:
        scalable_bloom = ScalableBloomFilter()

    @app.post("/api/v1/scalablebloom/add")
    async def api_sb_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "element" not in body:
            return JSONResponse({"error": "element is required"}, status_code=422)
        added = scalable_bloom.add(str(body["element"]))
        return JSONResponse({"element": str(body["element"]), "added": added,
                            "count": scalable_bloom.count})

    @app.get("/api/v1/scalablebloom/contains")
    async def api_sb_contains(element: str) -> JSONResponse:
        return JSONResponse({"element": element, "contains": scalable_bloom.contains(element)})

    @app.get("/api/v1/scalablebloom/stats")
    async def api_sb_stats() -> JSONResponse:
        return JSONResponse(scalable_bloom.stats())

    @app.delete("/api/v1/scalablebloom/reset")
    async def api_sb_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            scalable_bloom.reset(
                body.get("initial_capacity"), body.get("error_rate"),
                body.get("ratio"), body.get("growth"), body.get("seed"),
            )
        except ScalableBloomError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(scalable_bloom.stats())

    return scalable_bloom
