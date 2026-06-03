"""Phase 147 — Sovereign Sqrt Decomposition HTTP routes.

Exposes a :class:`~pradyos.core.sqrt_decomposition.SqrtDecomposition` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_sqrtdecomp_routes`, called *inside* the factory — the array lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton. All routes
are static (no path parameters), so none can shadow another.

An out-of-range index, ``lo > hi``, non-numeric delta/value, or an operation on an empty array
is a request error → **HTTP 422** (query indices use the ``Query(ge=0)`` idiom; the array-bound
and ordering rules are caught from the core).

Routes (mounted under ``/api/v1/sqrtdecomp``):
  POST   /api/v1/sqrtdecomp/range_add    body ``{"lo", "hi", "delta"}`` — ``{lo, hi, total}``
  GET    /api/v1/sqrtdecomp/range_sum    query ``?lo=&hi=`` — ``{lo, hi, sum}``
  GET    /api/v1/sqrtdecomp/point_query  query ``?i=`` — ``{i, value}``
  POST   /api/v1/sqrtdecomp/update       body ``{"i", "value"}`` — ``{i, value, total}``
  GET    /api/v1/sqrtdecomp/stats         ``{size, block_size, num_blocks, total}``
  DELETE /api/v1/sqrtdecomp/reset         body ``{"values"?}`` — rebuild from array / clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.sqrt_decomposition import SqrtDecomposition, SqrtDecompositionError


def register_sqrtdecomp_routes(app: Any, sqrt_decomposition: Any | None = None) -> Any:
    """Register the /api/v1/sqrtdecomp routes on ``app``; return the structure used.

    ``sqrt_decomposition`` defaults to a fresh 16-zero :class:`SqrtDecomposition` owned by this
    app instance (factory scope — never a module-level global)."""
    if sqrt_decomposition is None:
        sqrt_decomposition = SqrtDecomposition([0] * 16)

    @app.post("/api/v1/sqrtdecomp/range_add")
    async def api_sd_range_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "lo" not in body or "hi" not in body or "delta" not in body:
            return JSONResponse({"error": "lo, hi and delta are required"}, status_code=422)
        try:
            sqrt_decomposition.range_add(body["lo"], body["hi"], body["delta"])
        except SqrtDecompositionError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": body["lo"], "hi": body["hi"], "total": sqrt_decomposition.total()})

    @app.get("/api/v1/sqrtdecomp/range_sum")
    async def api_sd_range_sum(lo: int = Query(..., ge=0), hi: int = Query(..., ge=0)) -> JSONResponse:
        try:
            s = sqrt_decomposition.range_sum(lo, hi)
        except SqrtDecompositionError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": lo, "hi": hi, "sum": s})

    @app.get("/api/v1/sqrtdecomp/point_query")
    async def api_sd_point(i: int = Query(..., ge=0)) -> JSONResponse:
        try:
            v = sqrt_decomposition.point_query(i)
        except SqrtDecompositionError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": i, "value": v})

    @app.post("/api/v1/sqrtdecomp/update")
    async def api_sd_update(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "i" not in body or "value" not in body:
            return JSONResponse({"error": "i and value are required"}, status_code=422)
        try:
            sqrt_decomposition.update(body["i"], body["value"])
        except SqrtDecompositionError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": body["i"], "value": body["value"], "total": sqrt_decomposition.total()})

    @app.get("/api/v1/sqrtdecomp/stats")
    async def api_sd_stats() -> JSONResponse:
        return JSONResponse(sqrt_decomposition.stats())

    @app.delete("/api/v1/sqrtdecomp/reset")
    async def api_sd_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            if "values" in body and body["values"] is not None:
                sqrt_decomposition.build(body["values"])
            else:
                sqrt_decomposition.reset()
        except SqrtDecompositionError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(sqrt_decomposition.stats())

    return sqrt_decomposition
