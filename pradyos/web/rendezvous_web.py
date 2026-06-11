"""Phase 119 — Sovereign Rendezvous Hashing HTTP routes.

Exposes a :class:`~pradyos.core.rendezvous_hash.RendezvousHash` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_rendezvous_routes`, called *inside* the factory — the ring lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

Assigning / requesting replicas with **no nodes** is a state error → **HTTP 400**
(distinct from the 422 used for request-shape / weight / ``k`` validation).

Routes (mounted under ``/api/v1/rendezvous``):
  POST   /api/v1/rendezvous/nodes     body ``{"node": x, "weight"?: float}`` — add / re-weight a node
  DELETE /api/v1/rendezvous/nodes     body ``{"node": x}`` — remove a node
  GET    /api/v1/rendezvous/assign    ``?key=`` — ``{key, node}``; 400 if no nodes
  GET    /api/v1/rendezvous/replicas  ``?key=&k=`` — ``{key, k, replicas}``; 400 if no nodes
  GET    /api/v1/rendezvous/stats     ``{num_nodes, nodes, total_weight, seed}``
  DELETE /api/v1/rendezvous/reset     body ``{"seed"?}`` — remove all nodes / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.rendezvous_hash import RendezvousError, RendezvousHash


def register_rendezvous_routes(app: Any, rendezvous: Any | None = None) -> Any:
    """Register the /api/v1/rendezvous routes on ``app``; return the ring used.

    ``rendezvous`` defaults to a fresh :class:`RendezvousHash` owned by this app
    instance (factory scope — never a module-level global)."""
    if rendezvous is None:
        rendezvous = RendezvousHash()

    @app.post("/api/v1/rendezvous/nodes")
    async def api_rdv_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "node" not in body:
            return JSONResponse({"error": "node is required"}, status_code=422)
        weight = body.get("weight", 1.0)
        try:
            rendezvous.add_node(str(body["node"]), weight)
        except RendezvousError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(
            {"node": str(body["node"]), "weight": weight, "num_nodes": len(rendezvous)}
        )

    @app.delete("/api/v1/rendezvous/nodes")
    async def api_rdv_remove(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "node" not in body:
            return JSONResponse({"error": "node is required"}, status_code=422)
        removed = rendezvous.remove_node(str(body["node"]))
        return JSONResponse(
            {"node": str(body["node"]), "removed": removed, "num_nodes": len(rendezvous)}
        )

    @app.get("/api/v1/rendezvous/assign")
    async def api_rdv_assign(key: str) -> JSONResponse:
        try:
            node = rendezvous.assign(key)
        except RendezvousError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"key": key, "node": node})

    @app.get("/api/v1/rendezvous/replicas")
    async def api_rdv_replicas(key: str, k: int = Query(ge=1)) -> JSONResponse:
        try:
            replicas = rendezvous.get_replicas(key, k)
        except RendezvousError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"key": key, "k": k, "replicas": replicas})

    @app.get("/api/v1/rendezvous/stats")
    async def api_rdv_stats() -> JSONResponse:
        return JSONResponse(rendezvous.stats())

    @app.delete("/api/v1/rendezvous/reset")
    async def api_rdv_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            rendezvous.reset(body.get("seed"))
        except RendezvousError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(rendezvous.stats())

    return rendezvous
