"""Phase 92 — Sovereign KLL Sketch HTTP routes.

Exposes a :class:`~pradyos.core.kll_sketch.KLLSketch` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_kll_sketch_routes`, called *inside* the factory — the sketch
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Like Phase 91's Greenwald–Khanna this estimates quantiles, but it is randomized,
space-optimal, and — uniquely — natively **mergeable**: ``/merge`` folds a second
batch (built into a temporary sketch) into the shared one, the basis for
distributed aggregation.

Routes (mounted under ``/api/v1/kll``):
  POST /api/v1/kll/insert  body ``{"value": x}`` or ``{"values": [...]}``
  GET  /api/v1/kll/query   ``?phi=0.95`` — the φ-quantile (422 if empty / φ∉[0,1])
  POST /api/v1/kll/merge   body ``{"values": [...]}`` — build a sketch and merge it in
  GET  /api/v1/kll/stats   ``{k, n, num_levels, num_compactors, sketch_size_ratio}``
  POST /api/v1/kll/reset   body ``{"k"?: int, "seed"?: int}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.kll_sketch import KLLError, KLLSketch

DEFAULT_K = 200


def register_kll_sketch_routes(app: Any, kll: Any | None = None) -> Any:
    """Register the /api/v1/kll routes on ``app``; return the sketch used.

    ``kll`` defaults to a fresh :class:`KLLSketch` owned by this app instance
    (factory scope — never a module-level global)."""
    if kll is None:
        kll = KLLSketch(DEFAULT_K)

    @app.post("/api/v1/kll/insert")
    async def api_kll_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "value or values is required"}, status_code=422)
        try:
            if "values" in body:
                values = body.get("values")
                if not isinstance(values, list):
                    return JSONResponse({"error": "values must be a list"}, status_code=422)
                added = kll.update_many(values)
            elif "value" in body:
                kll.update(body.get("value"))
                added = 1
            else:
                return JSONResponse({"error": "value or values is required"}, status_code=422)
        except KLLError:
            return JSONResponse({"error": "value must be a number"}, status_code=422)
        return JSONResponse({"inserted": added, "n": kll.count()})

    @app.get("/api/v1/kll/query")
    async def api_kll_query(phi: float = Query(ge=0.0, le=1.0)) -> JSONResponse:
        value = kll.query(phi)
        if value is None:
            return JSONResponse({"error": "sketch is empty"}, status_code=422)
        return JSONResponse({"phi": phi, "quantile": value, "n": kll.count()})

    @app.post("/api/v1/kll/merge")
    async def api_kll_merge(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "values" not in body:
            return JSONResponse({"error": "values is required"}, status_code=422)
        values = body.get("values")
        if not isinstance(values, list):
            return JSONResponse({"error": "values must be a list"}, status_code=422)
        try:
            other = KLLSketch(k=kll.k, seed=kll.seed)
            other.update_many(values)
        except KLLError:
            return JSONResponse({"error": "values must be numbers"}, status_code=422)
        kll.merge(other)
        return JSONResponse({"merged": len(values), "n": kll.count()})

    @app.get("/api/v1/kll/stats")
    async def api_kll_stats() -> JSONResponse:
        return JSONResponse(kll.stats())

    @app.post("/api/v1/kll/reset")
    async def api_kll_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            kll.reset(body.get("k"), body.get("seed"))
        except KLLError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(kll.stats())

    return kll
