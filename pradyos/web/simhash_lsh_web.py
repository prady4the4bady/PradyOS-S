"""Phase 126 — Sovereign Cosine / Random-Hyperplane LSH HTTP routes.

Exposes a :class:`~pradyos.core.simhash_lsh.SimHashLSH` over REST. Routes are registered
onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_simhashlsh_routes`, called *inside* the factory — the index lives in
factory scope (passed in, or created fresh per app), so there is no module-level singleton.
All routes are static (no path parameters), so none can shadow another.

Items are identified by a JSON ``id`` and described by a fixed-length ``vector``; ``query``
returns indexed ids sharing an LSH band bucket with the query vector, refined by estimated
**cosine** similarity and an optional ``threshold`` (in ``[-1, 1]``). A wrong-dimension
vector or out-of-range threshold is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/simhashlsh``):
  POST   /api/v1/simhashlsh/insert  body ``{"id": x, "vector": [...]}`` — index an item
  POST   /api/v1/simhashlsh/query   body ``{"vector": [...], "threshold"?: float}`` — similar items
  DELETE /api/v1/simhashlsh/remove  body ``{"id": x}`` — remove an item
  GET    /api/v1/simhashlsh/stats   ``{num_items, dim, bands, rows, num_perm, seed}``
  DELETE /api/v1/simhashlsh/reset   body ``{"dim"?, "bands"?, "rows"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.simhash_lsh import SimHashLSH, SimHashLSHError


def register_simhashlsh_routes(app: Any, simhash_lsh: Any | None = None) -> Any:
    """Register the /api/v1/simhashlsh routes on ``app``; return the index used.

    ``simhash_lsh`` defaults to a fresh :class:`SimHashLSH` owned by this app instance
    (factory scope — never a module-level global)."""
    if simhash_lsh is None:
        simhash_lsh = SimHashLSH()

    @app.post("/api/v1/simhashlsh/insert")
    async def api_simhash_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if (
            not isinstance(body, dict)
            or "id" not in body
            or not isinstance(body.get("vector"), list)
        ):
            return JSONResponse({"error": "id and vector list are required"}, status_code=422)
        try:
            simhash_lsh.insert(body["id"], body["vector"])
        except SimHashLSHError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"id": body["id"], "num_items": len(simhash_lsh)})

    @app.post("/api/v1/simhashlsh/query")
    async def api_simhash_query(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("vector"), list):
            return JSONResponse({"error": "vector list is required"}, status_code=422)
        try:
            matches = simhash_lsh.query(body["vector"], body.get("threshold", 0.0))
        except SimHashLSHError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        candidates = [{"id": cid, "similarity": round(sim, 6)} for cid, sim in matches]
        return JSONResponse({"candidates": candidates, "count": len(candidates)})

    @app.delete("/api/v1/simhashlsh/remove")
    async def api_simhash_remove(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "id" not in body:
            return JSONResponse({"error": "id is required"}, status_code=422)
        removed = simhash_lsh.remove(body["id"])
        return JSONResponse({"id": body["id"], "removed": removed, "num_items": len(simhash_lsh)})

    @app.get("/api/v1/simhashlsh/stats")
    async def api_simhash_stats() -> JSONResponse:
        return JSONResponse(simhash_lsh.stats())

    @app.delete("/api/v1/simhashlsh/reset")
    async def api_simhash_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            simhash_lsh.reset(
                body.get("dim"), body.get("bands"), body.get("rows"), body.get("seed")
            )
        except SimHashLSHError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(simhash_lsh.stats())

    return simhash_lsh
