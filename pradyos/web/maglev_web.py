"""Phase 120 — Sovereign Maglev Hashing HTTP routes.

Exposes a :class:`~pradyos.core.maglev.MaglevHash` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_maglev_routes`, called *inside* the factory — the table lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton. All
routes are static (no path parameters), so none can shadow another.

A lookup with **no nodes** is a state error → **HTTP 400**; an ``add`` that would exceed
the table size is likewise a **400** (distinct from the 422 used for request-shape /
config validation).

Routes (mounted under ``/api/v1/maglev``):
  POST   /api/v1/maglev/nodes   body ``{"node": x}`` — add a node (rebuilds the table)
  DELETE /api/v1/maglev/nodes   body ``{"node": x}`` — remove a node (rebuilds)
  GET    /api/v1/maglev/lookup  ``?key=`` — ``{key, node}``; 400 if no nodes
  GET    /api/v1/maglev/stats   ``{num_nodes, table_size, nodes, min_load, max_load, load_ratio, seed}``
  DELETE /api/v1/maglev/reset   body ``{"table_size"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.maglev import MaglevHash, MaglevError


def register_maglev_routes(app: Any, maglev: Any | None = None) -> Any:
    """Register the /api/v1/maglev routes on ``app``; return the table used.

    ``maglev`` defaults to a fresh :class:`MaglevHash` owned by this app instance
    (factory scope — never a module-level global)."""
    if maglev is None:
        maglev = MaglevHash()

    @app.post("/api/v1/maglev/nodes")
    async def api_maglev_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "node" not in body:
            return JSONResponse({"error": "node is required"}, status_code=422)
        try:
            added = maglev.add_node(str(body["node"]))
        except MaglevError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"node": str(body["node"]), "added": added, "num_nodes": len(maglev)})

    @app.delete("/api/v1/maglev/nodes")
    async def api_maglev_remove(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "node" not in body:
            return JSONResponse({"error": "node is required"}, status_code=422)
        removed = maglev.remove_node(str(body["node"]))
        return JSONResponse({"node": str(body["node"]), "removed": removed, "num_nodes": len(maglev)})

    @app.get("/api/v1/maglev/lookup")
    async def api_maglev_lookup(key: str) -> JSONResponse:
        try:
            node = maglev.lookup(key)
        except MaglevError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"key": key, "node": node})

    @app.get("/api/v1/maglev/stats")
    async def api_maglev_stats() -> JSONResponse:
        return JSONResponse(maglev.stats())

    @app.delete("/api/v1/maglev/reset")
    async def api_maglev_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            maglev.reset(body.get("table_size"), body.get("seed"))
        except MaglevError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(maglev.stats())

    return maglev
