"""Phase 141 — Sovereign Suffix Array HTTP routes.

Exposes a :class:`~pradyos.core.suffix_array.SuffixArray` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_suffixarray_routes`, called *inside* the factory — the index lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton. All routes
are static (no path parameters), so none can shadow another.

A non-string text/pattern or an empty pattern is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/suffixarray``):
  POST   /api/v1/suffixarray/build   body ``{"text": "..."}`` — returns stats
  POST   /api/v1/suffixarray/search  body ``{"pattern": "..."}`` — ``{pattern, contains, count, positions}``
  GET    /api/v1/suffixarray/array    ``{suffix_array, lcp_array}``
  GET    /api/v1/suffixarray/stats     ``{size, num_suffixes, distinct_substrings}``
  DELETE /api/v1/suffixarray/reset     (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.suffix_array import SuffixArray, SuffixArrayError


def register_suffixarray_routes(app: Any, suffix_array: Any | None = None) -> Any:
    """Register the /api/v1/suffixarray routes on ``app``; return the index used.

    ``suffix_array`` defaults to a fresh (empty) :class:`SuffixArray` owned by this app instance
    (factory scope — never a module-level global)."""
    if suffix_array is None:
        suffix_array = SuffixArray()

    @app.post("/api/v1/suffixarray/build")
    async def api_sa_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("text"), str):
            return JSONResponse({"error": "text string is required"}, status_code=422)
        try:
            suffix_array.build(body["text"])
        except SuffixArrayError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(suffix_array.stats())

    @app.post("/api/v1/suffixarray/search")
    async def api_sa_search(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "pattern" not in body:
            return JSONResponse({"error": "pattern is required"}, status_code=422)
        try:
            pos = suffix_array.positions(body["pattern"])
        except SuffixArrayError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"pattern": body["pattern"], "contains": len(pos) > 0,
                             "count": len(pos), "positions": pos})

    @app.get("/api/v1/suffixarray/array")
    async def api_sa_array() -> JSONResponse:
        return JSONResponse({"suffix_array": suffix_array.suffix_array(),
                             "lcp_array": suffix_array.lcp_array()})

    @app.get("/api/v1/suffixarray/stats")
    async def api_sa_stats() -> JSONResponse:
        return JSONResponse(suffix_array.stats())

    @app.delete("/api/v1/suffixarray/reset")
    async def api_sa_reset() -> JSONResponse:
        suffix_array.reset()
        return JSONResponse(suffix_array.stats())

    return suffix_array
