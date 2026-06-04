"""Phase 163 — Sovereign Lazy Segment Tree HTTP routes.

Exposes a :class:`~pradyos.core.lazy_segment_tree.LazySegmentTree` over REST. Routes are registered
onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_lazyseg_routes`,
called *inside* the factory — the tree lives in factory scope (passed in, or created fresh per app),
so there is no module-level singleton. All routes are static (no path parameters), so none can
shadow another.

An out-of-range index, ``lo > hi``, or a non-numeric delta/value is a request error → **HTTP 422**
(query indices use the ``Query(ge=0)`` idiom; the upper bound and ordering are caught from the core).

Routes (mounted under ``/api/v1/lazysegtree``):
  POST   /api/v1/lazysegtree/build         body ``{"values": [...]}`` — rebuild, returns stats
  POST   /api/v1/lazysegtree/range_add     body ``{"lo", "hi", "delta"}`` — ``{lo, hi, total}``
  POST   /api/v1/lazysegtree/range_assign  body ``{"lo", "hi", "value"}`` — ``{lo, hi, total}``
  GET    /api/v1/lazysegtree/range_sum     query ``?lo=&hi=`` — ``{lo, hi, sum}``
  GET    /api/v1/lazysegtree/range_min     query ``?lo=&hi=`` — ``{lo, hi, min}``
  GET    /api/v1/lazysegtree/range_max     query ``?lo=&hi=`` — ``{lo, hi, max}``
  GET    /api/v1/lazysegtree/point_query   query ``?i=`` — ``{i, value}``
  GET    /api/v1/lazysegtree/stats          ``{size, total, min, max}``
  DELETE /api/v1/lazysegtree/reset          body ``{"values"?}`` — rebuild / clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.lazy_segment_tree import LazySegmentTree, LazySegmentTreeError


def register_lazyseg_routes(app: Any, lazy_segment_tree: Any | None = None) -> Any:
    """Register the /api/v1/lazysegtree routes on ``app``; return the tree used.

    ``lazy_segment_tree`` defaults to a fresh 16-zero :class:`LazySegmentTree` owned by this app
    instance (factory scope — never a module-level global)."""
    if lazy_segment_tree is None:
        lazy_segment_tree = LazySegmentTree([0] * 16)
    lst = lazy_segment_tree

    @app.post("/api/v1/lazysegtree/build")
    async def api_ls_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "values" not in body:
            return JSONResponse({"error": "values is required"}, status_code=422)
        try:
            lst.build(body["values"])
        except LazySegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(lst.stats())

    @app.post("/api/v1/lazysegtree/range_add")
    async def api_ls_range_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "lo" not in body or "hi" not in body or "delta" not in body:
            return JSONResponse({"error": "lo, hi and delta are required"}, status_code=422)
        try:
            lst.range_add(body["lo"], body["hi"], body["delta"])
        except LazySegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": body["lo"], "hi": body["hi"], "total": lst.stats()["total"]})

    @app.post("/api/v1/lazysegtree/range_assign")
    async def api_ls_range_assign(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "lo" not in body or "hi" not in body or "value" not in body:
            return JSONResponse({"error": "lo, hi and value are required"}, status_code=422)
        try:
            lst.range_assign(body["lo"], body["hi"], body["value"])
        except LazySegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": body["lo"], "hi": body["hi"], "total": lst.stats()["total"]})

    @app.get("/api/v1/lazysegtree/range_sum")
    async def api_ls_range_sum(lo: int = Query(..., ge=0), hi: int = Query(..., ge=0)) -> JSONResponse:
        try:
            s = lst.range_sum(lo, hi)
        except LazySegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": lo, "hi": hi, "sum": s})

    @app.get("/api/v1/lazysegtree/range_min")
    async def api_ls_range_min(lo: int = Query(..., ge=0), hi: int = Query(..., ge=0)) -> JSONResponse:
        try:
            m = lst.range_min(lo, hi)
        except LazySegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": lo, "hi": hi, "min": m})

    @app.get("/api/v1/lazysegtree/range_max")
    async def api_ls_range_max(lo: int = Query(..., ge=0), hi: int = Query(..., ge=0)) -> JSONResponse:
        try:
            m = lst.range_max(lo, hi)
        except LazySegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": lo, "hi": hi, "max": m})

    @app.get("/api/v1/lazysegtree/point_query")
    async def api_ls_point(i: int = Query(..., ge=0)) -> JSONResponse:
        try:
            v = lst.point_query(i)
        except LazySegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": i, "value": v})

    @app.get("/api/v1/lazysegtree/stats")
    async def api_ls_stats() -> JSONResponse:
        return JSONResponse(lst.stats())

    @app.delete("/api/v1/lazysegtree/reset")
    async def api_ls_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            if "values" in body and body["values"] is not None:
                lst.build(body["values"])
            else:
                lst.reset()
        except LazySegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(lst.stats())

    return lst
