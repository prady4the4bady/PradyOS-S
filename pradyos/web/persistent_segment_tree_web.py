"""Phase 149 — Sovereign Persistent Segment Tree HTTP routes.

Exposes a :class:`~pradyos.core.persistent_segment_tree.PersistentSegmentTree` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_perseg_routes`, called *inside* the factory — the tree (and its whole version
history) lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can shadow another.

A bad version, out-of-range index, ``lo > hi``, non-numeric value, or an empty/invalid build is a
request error → **HTTP 422** (query indices use the ``Query(ge=0)`` idiom; the version-range,
array-bound and ordering rules are caught from the core).

Routes (mounted under ``/api/v1/perseg``):
  POST   /api/v1/perseg/build         body ``{"values": [...]}`` — rebuild as version 0
  POST   /api/v1/perseg/update        body ``{"version", "i", "value"}`` — ``{version, i, value, num_versions}``
  GET    /api/v1/perseg/range_sum     query ``?version=&lo=&hi=`` — ``{version, lo, hi, sum}``
  GET    /api/v1/perseg/point_query   query ``?version=&i=`` — ``{version, i, value}``
  GET    /api/v1/perseg/stats          ``{size, num_versions, nodes}``
  DELETE /api/v1/perseg/reset          discard all versions
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.persistent_segment_tree import (
    PersistentSegmentTree, PersistentSegmentTreeError)


def register_perseg_routes(app: Any, persistent_segment_tree: Any | None = None) -> Any:
    """Register the /api/v1/perseg routes on ``app``; return the structure used.

    ``persistent_segment_tree`` defaults to a fresh 16-zero :class:`PersistentSegmentTree`
    (version 0) owned by this app instance (factory scope — never a module-level global)."""
    if persistent_segment_tree is None:
        persistent_segment_tree = PersistentSegmentTree([0] * 16)
    pst = persistent_segment_tree

    @app.post("/api/v1/perseg/build")
    async def api_perseg_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "values" not in body:
            return JSONResponse({"error": "values is required"}, status_code=422)
        try:
            pst.build(body["values"])
        except PersistentSegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(pst.stats())

    @app.post("/api/v1/perseg/update")
    async def api_perseg_update(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "version" not in body or "i" not in body or "value" not in body:
            return JSONResponse({"error": "version, i and value are required"}, status_code=422)
        try:
            new_version = pst.update(body["version"], body["i"], body["value"])
        except PersistentSegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"version": new_version, "i": body["i"], "value": body["value"],
                             "num_versions": pst.num_versions})

    @app.get("/api/v1/perseg/range_sum")
    async def api_perseg_range_sum(version: int = Query(..., ge=0),
                                   lo: int = Query(..., ge=0),
                                   hi: int = Query(..., ge=0)) -> JSONResponse:
        try:
            s = pst.range_sum(version, lo, hi)
        except PersistentSegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"version": version, "lo": lo, "hi": hi, "sum": s})

    @app.get("/api/v1/perseg/point_query")
    async def api_perseg_point(version: int = Query(..., ge=0), i: int = Query(..., ge=0)) -> JSONResponse:
        try:
            v = pst.point_query(version, i)
        except PersistentSegmentTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"version": version, "i": i, "value": v})

    @app.get("/api/v1/perseg/stats")
    async def api_perseg_stats() -> JSONResponse:
        return JSONResponse(pst.stats())

    @app.delete("/api/v1/perseg/reset")
    async def api_perseg_reset() -> JSONResponse:
        pst.reset()
        return JSONResponse(pst.stats())

    return pst
