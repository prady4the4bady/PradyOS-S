"""Phase 115 — Sovereign MinHash LSH HTTP routes.

Exposes a :class:`~pradyos.core.minhash_lsh.MinHashLSH` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_minhashlsh_routes`, called *inside* the factory — the index lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

Items are identified by a JSON ``id`` and described by a ``tokens`` list (their set);
``query`` returns the indexed ids sharing an LSH band bucket with the query set,
refined by estimated Jaccard similarity and an optional ``threshold``.

Routes (mounted under ``/api/v1/minhashlsh``):
  POST   /api/v1/minhashlsh/insert  body ``{"id": x, "tokens": [...]}`` — index an item
  POST   /api/v1/minhashlsh/query   body ``{"tokens": [...], "threshold"?: float}`` — similar items
  DELETE /api/v1/minhashlsh/remove  body ``{"id": x}`` — remove an item
  GET    /api/v1/minhashlsh/stats   ``{num_items, bands, rows, num_perm, threshold_estimate, seed}``
  DELETE /api/v1/minhashlsh/reset   body ``{"bands"?, "rows"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.minhash_lsh import MinHashLSH, MinHashLSHError


def register_minhashlsh_routes(app: Any, minhash_lsh: Any | None = None) -> Any:
    """Register the /api/v1/minhashlsh routes on ``app``; return the index used.

    ``minhash_lsh`` defaults to a fresh :class:`MinHashLSH` owned by this app instance
    (factory scope — never a module-level global)."""
    if minhash_lsh is None:
        minhash_lsh = MinHashLSH()

    @app.post("/api/v1/minhashlsh/insert")
    async def api_lsh_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if (
            not isinstance(body, dict)
            or "id" not in body
            or not isinstance(body.get("tokens"), list)
        ):
            return JSONResponse({"error": "id and tokens list are required"}, status_code=422)
        minhash_lsh.insert(body["id"], body["tokens"])
        return JSONResponse({"id": body["id"], "num_items": len(minhash_lsh)})

    @app.post("/api/v1/minhashlsh/query")
    async def api_lsh_query(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("tokens"), list):
            return JSONResponse({"error": "tokens list is required"}, status_code=422)
        threshold = body.get("threshold", 0.0)
        try:
            matches = minhash_lsh.query(body["tokens"], threshold)
        except MinHashLSHError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        candidates = [{"id": cid, "similarity": round(sim, 6)} for cid, sim in matches]
        return JSONResponse({"candidates": candidates, "count": len(candidates)})

    @app.delete("/api/v1/minhashlsh/remove")
    async def api_lsh_remove(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "id" not in body:
            return JSONResponse({"error": "id is required"}, status_code=422)
        removed = minhash_lsh.remove(body["id"])
        return JSONResponse({"id": body["id"], "removed": removed, "num_items": len(minhash_lsh)})

    @app.get("/api/v1/minhashlsh/stats")
    async def api_lsh_stats() -> JSONResponse:
        return JSONResponse(minhash_lsh.stats())

    @app.delete("/api/v1/minhashlsh/reset")
    async def api_lsh_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            minhash_lsh.reset(body.get("bands"), body.get("rows"), body.get("seed"))
        except MinHashLSHError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(minhash_lsh.stats())

    return minhash_lsh
