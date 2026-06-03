"""Phase 138 — Sovereign Sparse Table HTTP routes.

Exposes a :class:`~pradyos.core.sparse_table.SparseTable` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_sparsetable_routes`, called *inside* the factory — the table lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton. All routes
are static (no path parameters), so none can shadow another.

A malformed array/op or an out-of-range query is a request error → **HTTP 422** (query indices
use the ``Query(ge=…)`` idiom; the `0 ≤ lo < hi ≤ n` rule is caught from the core).

Routes (mounted under ``/api/v1/sparsetable``):
  POST   /api/v1/sparsetable/build  body ``{"values": [...], "op"?: "min"|"max"}`` — returns stats
  GET    /api/v1/sparsetable/query  query ``?lo=&hi=`` — ``{lo, hi, value}`` (half-open `[lo, hi)`)
  GET    /api/v1/sparsetable/get    query ``?i=`` — ``{i, value}``
  GET    /api/v1/sparsetable/stats   ``{size, op, levels}``
  DELETE /api/v1/sparsetable/reset   (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.sparse_table import SparseTable, SparseTableError


def register_sparsetable_routes(app: Any, sparse_table: Any | None = None) -> Any:
    """Register the /api/v1/sparsetable routes on ``app``; return the table used.

    ``sparse_table`` defaults to a fresh (empty) :class:`SparseTable` owned by this app instance
    (factory scope — never a module-level global)."""
    if sparse_table is None:
        sparse_table = SparseTable()

    @app.post("/api/v1/sparsetable/build")
    async def api_st_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("values"), list):
            return JSONResponse({"error": "values list is required"}, status_code=422)
        try:
            sparse_table.build(body["values"], body.get("op", "min"))
        except SparseTableError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(sparse_table.stats())

    @app.get("/api/v1/sparsetable/query")
    async def api_st_query(lo: int = Query(..., ge=0), hi: int = Query(..., ge=1)) -> JSONResponse:
        try:
            value = sparse_table.query(lo, hi)
        except SparseTableError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": lo, "hi": hi, "value": value})

    @app.get("/api/v1/sparsetable/get")
    async def api_st_get(i: int = Query(..., ge=0)) -> JSONResponse:
        try:
            value = sparse_table.get(i)
        except SparseTableError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": i, "value": value})

    @app.get("/api/v1/sparsetable/stats")
    async def api_st_stats() -> JSONResponse:
        return JSONResponse(sparse_table.stats())

    @app.delete("/api/v1/sparsetable/reset")
    async def api_st_reset() -> JSONResponse:
        sparse_table.reset()
        return JSONResponse(sparse_table.stats())

    return sparse_table
