"""Phase 162 — Sovereign Implicit Treap HTTP routes.

Exposes an :class:`~pradyos.core.implicit_treap.ImplicitTreap` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_implicittreap_routes`,
called *inside* the factory — the sequence lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so none
can shadow another.

An out-of-range index, a non-numeric value, or an inverted range is a request error → **HTTP 422**
(query indices use the ``Query(ge=0)`` idiom; the upper bound is caught from the core).

Routes (mounted under ``/api/v1/implicittreap``):
  POST   /api/v1/implicittreap/insert     body ``{"index", "value"}`` — ``{index, value, size}``
  POST   /api/v1/implicittreap/delete     body ``{"index"}`` — ``{index, value, size}``
  GET    /api/v1/implicittreap/get        query ``?index=`` — ``{index, value}``
  POST   /api/v1/implicittreap/set        body ``{"index", "value"}`` — ``{index, value, size}``
  GET    /api/v1/implicittreap/range_sum  query ``?lo=&hi=`` — ``{lo, hi, sum}``
  GET    /api/v1/implicittreap/list        ``{values, size}``
  GET    /api/v1/implicittreap/stats       ``{size, total}``
  DELETE /api/v1/implicittreap/reset       empty the sequence
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.implicit_treap import ImplicitTreap, ImplicitTreapError


def register_implicittreap_routes(app: Any, implicit_treap: Any | None = None) -> Any:
    """Register the /api/v1/implicittreap routes on ``app``; return the sequence used.

    ``implicit_treap`` defaults to a fresh empty :class:`ImplicitTreap` owned by this app instance
    (factory scope — never a module-level global)."""
    if implicit_treap is None:
        implicit_treap = ImplicitTreap()
    it = implicit_treap

    @app.post("/api/v1/implicittreap/insert")
    async def api_it_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "index" not in body or "value" not in body:
            return JSONResponse({"error": "index and value are required"}, status_code=422)
        try:
            it.insert(body["index"], body["value"])
        except ImplicitTreapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"index": body["index"], "value": body["value"], "size": it.size})

    @app.post("/api/v1/implicittreap/delete")
    async def api_it_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "index" not in body:
            return JSONResponse({"error": "index is required"}, status_code=422)
        try:
            value = it.delete(body["index"])
        except ImplicitTreapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"index": body["index"], "value": value, "size": it.size})

    @app.get("/api/v1/implicittreap/get")
    async def api_it_get(index: int = Query(..., ge=0)) -> JSONResponse:
        try:
            value = it.get(index)
        except ImplicitTreapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"index": index, "value": value})

    @app.post("/api/v1/implicittreap/set")
    async def api_it_set(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "index" not in body or "value" not in body:
            return JSONResponse({"error": "index and value are required"}, status_code=422)
        try:
            it.set(body["index"], body["value"])
        except ImplicitTreapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"index": body["index"], "value": body["value"], "size": it.size})

    @app.get("/api/v1/implicittreap/range_sum")
    async def api_it_range_sum(
        lo: int = Query(..., ge=0), hi: int = Query(..., ge=0)
    ) -> JSONResponse:
        try:
            s = it.range_sum(lo, hi)
        except ImplicitTreapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": lo, "hi": hi, "sum": s})

    @app.get("/api/v1/implicittreap/list")
    async def api_it_list() -> JSONResponse:
        values = it.to_list()
        return JSONResponse({"values": values, "size": len(values)})

    @app.get("/api/v1/implicittreap/stats")
    async def api_it_stats() -> JSONResponse:
        return JSONResponse(it.stats())

    @app.delete("/api/v1/implicittreap/reset")
    async def api_it_reset() -> JSONResponse:
        it.reset()
        return JSONResponse(it.stats())

    return it
