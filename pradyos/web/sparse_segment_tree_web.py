"""Phase 166 — Sovereign Sparse Segment Tree HTTP routes.

Exposes a :class:`~pradyos.core.sparse_segment_tree.SparseSegmentTree` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_sparseseg_routes`, called *inside* the factory — the tree lives in factory scope
(passed in, or created fresh per app), so there is no module-level singleton. All routes are static
(no path parameters), so none can shadow another.

An out-of-range index, ``lo > hi``, or a non-numeric delta/value is a request error → **HTTP 422**
(query indices use the ``Query(ge=0)`` idiom; the upper bound and ordering are caught from the core).

Routes (mounted under ``/api/v1/sparseseg``):
  POST   /api/v1/sparseseg/update        body ``{"index", "delta"}`` — ``{index, delta, total}``
  POST   /api/v1/sparseseg/point_assign  body ``{"index", "value"}`` — ``{index, value, total}``
  GET    /api/v1/sparseseg/range_sum     query ``?lo=&hi=`` — ``{lo, hi, sum}``
  GET    /api/v1/sparseseg/point_query   query ``?index=`` — ``{index, value}``
  GET    /api/v1/sparseseg/stats          ``{universe, num_nodes, total}``
  DELETE /api/v1/sparseseg/reset          discard all entries
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.sparse_segment_tree import SparseSegmentTree, SparseSegmentTreeError


def register_sparseseg_routes(app: Any, sparse_segment_tree: Any | None = None) -> Any:
    """Register the /api/v1/sparseseg routes on ``app``; return the tree used.

    ``sparse_segment_tree`` defaults to a fresh :class:`SparseSegmentTree` over ``[0, 2**62)`` owned
    by this app instance (factory scope — never a module-level global)."""
    if sparse_segment_tree is None:
        sparse_segment_tree = SparseSegmentTree()
    sst = sparse_segment_tree

    @app.post("/api/v1/sparseseg/update")
    async def api_ss_update(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "index" not in body or "delta" not in body:
            return JSONResponse({"error": "index and delta are required"}, status_code=422)
        try:
            sst.update(body["index"], body["delta"])
        except SparseSegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"index": body["index"], "delta": body["delta"], "total": sst.total()})

    @app.post("/api/v1/sparseseg/point_assign")
    async def api_ss_assign(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "index" not in body or "value" not in body:
            return JSONResponse({"error": "index and value are required"}, status_code=422)
        try:
            sst.point_assign(body["index"], body["value"])
        except SparseSegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"index": body["index"], "value": body["value"], "total": sst.total()})

    @app.get("/api/v1/sparseseg/range_sum")
    async def api_ss_range(lo: int = Query(..., ge=0), hi: int = Query(..., ge=0)) -> JSONResponse:
        try:
            s = sst.range_sum(lo, hi)
        except SparseSegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": lo, "hi": hi, "sum": s})

    @app.get("/api/v1/sparseseg/point_query")
    async def api_ss_point(index: int = Query(..., ge=0)) -> JSONResponse:
        try:
            v = sst.point_query(index)
        except SparseSegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"index": index, "value": v})

    @app.get("/api/v1/sparseseg/stats")
    async def api_ss_stats() -> JSONResponse:
        return JSONResponse(sst.stats())

    @app.delete("/api/v1/sparseseg/reset")
    async def api_ss_reset() -> JSONResponse:
        sst.reset()
        return JSONResponse(sst.stats())

    return sst
