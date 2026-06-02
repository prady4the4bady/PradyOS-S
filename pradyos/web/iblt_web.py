"""Phase 121 — Sovereign Invertible Bloom Lookup Table HTTP routes.

Exposes an :class:`~pradyos.core.iblt.InvertibleBloomLookupTable` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_iblt_routes`, called *inside* the factory — the table lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton.

Keys are stringified for a stable HTTP identity; values may be any JSON. ``get`` is
*best-effort* (it decodes a key only from a pure cell), whereas ``list`` decodes the whole
table by peeling — a state error (overloaded / not decodable) surfaces as **HTTP 400**.
``reconcile`` builds a throwaway compatible table from the posted pairs and returns the
**set difference** in both directions.

Routes (mounted under ``/api/v1/iblt``):
  POST   /api/v1/iblt/insert     body ``{"key": x, "value": v}`` — insert a pair
  DELETE /api/v1/iblt/delete     body ``{"key": x, "value": v}`` — delete a pair
  GET    /api/v1/iblt/get        ``?key=`` — ``{key, found, value}`` (best-effort)
  GET    /api/v1/iblt/list       ``{entries, count}``; 400 if not decodable
  POST   /api/v1/iblt/reconcile  body ``{"pairs": [[k, v], ...]}`` — ``{only_here, only_other}``; 400 if too large
  GET    /api/v1/iblt/stats      ``{size, num_cells, num_hashes, listable, seed}``
  DELETE /api/v1/iblt/reset      clear all cells
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.iblt import InvertibleBloomLookupTable, IBLTError


def register_iblt_routes(app: Any, iblt: Any | None = None) -> Any:
    """Register the /api/v1/iblt routes on ``app``; return the table used.

    ``iblt`` defaults to a fresh :class:`InvertibleBloomLookupTable` owned by this app
    instance (factory scope — never a module-level global)."""
    if iblt is None:
        iblt = InvertibleBloomLookupTable()

    @app.post("/api/v1/iblt/insert")
    async def api_iblt_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body or "value" not in body:
            return JSONResponse({"error": "key and value are required"}, status_code=422)
        iblt.insert(str(body["key"]), body["value"])
        return JSONResponse({"key": str(body["key"]), "size": len(iblt)})

    @app.delete("/api/v1/iblt/delete")
    async def api_iblt_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body or "value" not in body:
            return JSONResponse({"error": "key and value are required"}, status_code=422)
        iblt.delete(str(body["key"]), body["value"])
        return JSONResponse({"key": str(body["key"]), "size": len(iblt)})

    @app.get("/api/v1/iblt/get")
    async def api_iblt_get(key: str) -> JSONResponse:
        found = iblt.contains(key)
        return JSONResponse({"key": key, "found": found, "value": iblt.get(key) if found else None})

    @app.get("/api/v1/iblt/list")
    async def api_iblt_list() -> JSONResponse:
        try:
            entries = iblt.list_entries()
        except IBLTError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"entries": [{"key": k, "value": v} for k, v in entries],
                            "count": len(entries)})

    @app.post("/api/v1/iblt/reconcile")
    async def api_iblt_reconcile(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("pairs"), list):
            return JSONResponse({"error": "pairs list is required"}, status_code=422)
        other = InvertibleBloomLookupTable(num_cells=iblt.num_cells,
                                           num_hashes=iblt.num_hashes, seed=iblt.seed)
        for pair in body["pairs"]:
            if not isinstance(pair, list) or len(pair) != 2:
                return JSONResponse({"error": "each pair must be [key, value]"}, status_code=422)
            other.insert(str(pair[0]), pair[1])
        try:
            only_here, only_other = iblt.subtract(other).decode_difference()
        except IBLTError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({
            "only_here": [{"key": k, "value": v} for k, v in only_here],
            "only_other": [{"key": k, "value": v} for k, v in only_other],
        })

    @app.get("/api/v1/iblt/stats")
    async def api_iblt_stats() -> JSONResponse:
        return JSONResponse(iblt.stats())

    @app.delete("/api/v1/iblt/reset")
    async def api_iblt_reset() -> JSONResponse:
        iblt.reset()
        return JSONResponse(iblt.stats())

    return iblt
