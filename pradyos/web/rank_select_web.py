"""Phase 134 — Sovereign Rank/Select succinct-bitvector HTTP routes.

Exposes a :class:`~pradyos.core.rank_select.RankSelect` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_rankselect_routes`,
called *inside* the factory — the bitvector lives in factory scope (passed in, or created fresh
per app), so there is no module-level singleton. All routes are static (no path parameters),
so none can shadow another.

An out-of-range index/rank or malformed bit input is a request error → **HTTP 422** (query
params use the ``Query(ge=…)`` idiom; out-of-range against the vector length is caught from the
core).

Routes (mounted under ``/api/v1/rankselect``):
  POST   /api/v1/rankselect/build   body ``{"bits": "0101..." | [0,1,...]}`` — returns stats
  GET    /api/v1/rankselect/rank    query ``?i=&bit=`` — ``{i, bit, rank}`` (bit 1→rank1, 0→rank0)
  GET    /api/v1/rankselect/select  query ``?k=&bit=`` — ``{k, bit, position}`` (1-indexed)
  GET    /api/v1/rankselect/stats    ``{size, count1, count0, num_words, num_superblocks}``
  DELETE /api/v1/rankselect/reset    (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.rank_select import RankSelect, RankSelectError


def register_rankselect_routes(app: Any, rank_select: Any | None = None) -> Any:
    """Register the /api/v1/rankselect routes on ``app``; return the bitvector used.

    ``rank_select`` defaults to a fresh (empty) :class:`RankSelect` owned by this app instance
    (factory scope — never a module-level global)."""
    if rank_select is None:
        rank_select = RankSelect()

    @app.post("/api/v1/rankselect/build")
    async def api_rs_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "bits" not in body:
            return JSONResponse({"error": "bits is required"}, status_code=422)
        try:
            rank_select.build(body["bits"])
        except RankSelectError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(rank_select.stats())

    @app.get("/api/v1/rankselect/rank")
    async def api_rs_rank(i: int = Query(..., ge=0), bit: int = Query(1, ge=0, le=1)) -> JSONResponse:
        try:
            r = rank_select.rank1(i) if bit == 1 else rank_select.rank0(i)
        except RankSelectError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"i": i, "bit": bit, "rank": r})

    @app.get("/api/v1/rankselect/select")
    async def api_rs_select(k: int = Query(..., ge=1), bit: int = Query(1, ge=0, le=1)) -> JSONResponse:
        try:
            pos = rank_select.select1(k) if bit == 1 else rank_select.select0(k)
        except RankSelectError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"k": k, "bit": bit, "position": pos})

    @app.get("/api/v1/rankselect/stats")
    async def api_rs_stats() -> JSONResponse:
        return JSONResponse(rank_select.stats())

    @app.delete("/api/v1/rankselect/reset")
    async def api_rs_reset() -> JSONResponse:
        rank_select.reset()
        return JSONResponse(rank_select.stats())

    return rank_select
