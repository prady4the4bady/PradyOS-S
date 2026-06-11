"""Phase 135 — Sovereign Wavelet Tree HTTP routes.

Exposes a :class:`~pradyos.core.wavelet_tree.WaveletTree` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_wavelet_routes`,
called *inside* the factory — the index lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so
none can shadow another.

A wrong-kind symbol or out-of-range index is a request error → **HTTP 422** (the ``access``
index uses the ``Query(ge=0)`` idiom; range checks against the sequence are caught from the
core). ``select`` and ``range_count`` are exposed on the core class but not mounted here.

Routes (mounted under ``/api/v1/wavelet``):
  POST   /api/v1/wavelet/build     body ``{"sequence": [...]}`` — returns stats
  GET    /api/v1/wavelet/access    query ``?i=`` — ``{i, symbol}``
  POST   /api/v1/wavelet/rank      body ``{"symbol", "i"}`` — ``{symbol, i, rank}``
  POST   /api/v1/wavelet/quantile  body ``{"i", "j", "k"}`` — ``{i, j, k, symbol}``
  GET    /api/v1/wavelet/stats      ``{size, alphabet_size, height, kind}``
  DELETE /api/v1/wavelet/reset      (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.wavelet_tree import WaveletTree, WaveletTreeError


def register_wavelet_routes(app: Any, wavelet_tree: Any | None = None) -> Any:
    """Register the /api/v1/wavelet routes on ``app``; return the index used.

    ``wavelet_tree`` defaults to a fresh (empty) :class:`WaveletTree` owned by this app instance
    (factory scope — never a module-level global)."""
    if wavelet_tree is None:
        wavelet_tree = WaveletTree()

    @app.post("/api/v1/wavelet/build")
    async def api_wt_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("sequence"), list):
            return JSONResponse({"error": "sequence list is required"}, status_code=422)
        try:
            wavelet_tree.build(body["sequence"])
        except WaveletTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(wavelet_tree.stats())

    @app.get("/api/v1/wavelet/access")
    async def api_wt_access(i: int = Query(..., ge=0)) -> JSONResponse:
        try:
            symbol = wavelet_tree.access(i)
        except WaveletTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": i, "symbol": symbol})

    @app.post("/api/v1/wavelet/rank")
    async def api_wt_rank(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "symbol" not in body or "i" not in body:
            return JSONResponse({"error": "symbol and i are required"}, status_code=422)
        try:
            r = wavelet_tree.rank(body["symbol"], body["i"])
        except WaveletTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"symbol": body["symbol"], "i": body["i"], "rank": r})

    @app.post("/api/v1/wavelet/quantile")
    async def api_wt_quantile(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "i" not in body or "j" not in body or "k" not in body:
            return JSONResponse({"error": "i, j and k are required"}, status_code=422)
        try:
            symbol = wavelet_tree.quantile(body["i"], body["j"], body["k"])
        except WaveletTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": body["i"], "j": body["j"], "k": body["k"], "symbol": symbol})

    @app.get("/api/v1/wavelet/stats")
    async def api_wt_stats() -> JSONResponse:
        return JSONResponse(wavelet_tree.stats())

    @app.delete("/api/v1/wavelet/reset")
    async def api_wt_reset() -> JSONResponse:
        wavelet_tree.reset()
        return JSONResponse(wavelet_tree.stats())

    return wavelet_tree
