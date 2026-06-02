"""Phase 117 — Sovereign HyperMinHash HTTP routes.

Exposes a :class:`~pradyos.core.hyper_minhash.HyperMinHash` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_hyperminhash_routes`, called *inside* the factory — the sketch lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

The app holds one *primary* sketch (add / cardinality / stats / reset). For similarity,
``POST /compare`` builds a throwaway sketch from the request's ``tokens`` (using the
primary's ``p`` / ``r`` / ``seed`` so the two are compatible) and returns the estimated
Jaccard, union cardinality and intersection cardinality against the primary.

Routes (mounted under ``/api/v1/hyperminhash``):
  POST   /api/v1/hyperminhash/add          body ``{"element": x}`` — add to the primary sketch
  GET    /api/v1/hyperminhash/cardinality  ``{cardinality}`` — distinct-count estimate
  POST   /api/v1/hyperminhash/compare      body ``{"tokens": [...]}`` — ``{jaccard, union, intersection}`` vs primary
  GET    /api/v1/hyperminhash/stats        ``{p, r, num_buckets, filled, cardinality, seed}``
  DELETE /api/v1/hyperminhash/reset        body ``{"p"?, "r"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.hyper_minhash import HyperMinHash, HyperMinHashError


def register_hyperminhash_routes(app: Any, hyper_minhash: Any | None = None) -> Any:
    """Register the /api/v1/hyperminhash routes on ``app``; return the sketch used.

    ``hyper_minhash`` defaults to a fresh :class:`HyperMinHash` owned by this app
    instance (factory scope — never a module-level global)."""
    if hyper_minhash is None:
        hyper_minhash = HyperMinHash()

    @app.post("/api/v1/hyperminhash/add")
    async def api_hmh_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "element" not in body:
            return JSONResponse({"error": "element is required"}, status_code=422)
        hyper_minhash.add(body["element"])
        return JSONResponse({"element": body["element"], "cardinality": hyper_minhash.cardinality()})

    @app.get("/api/v1/hyperminhash/cardinality")
    async def api_hmh_cardinality() -> JSONResponse:
        return JSONResponse({"cardinality": hyper_minhash.cardinality()})

    @app.post("/api/v1/hyperminhash/compare")
    async def api_hmh_compare(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("tokens"), list):
            return JSONResponse({"error": "tokens list is required"}, status_code=422)
        other = HyperMinHash(p=hyper_minhash.p, r=hyper_minhash.r, seed=hyper_minhash.seed)
        other.add_many(body["tokens"])
        return JSONResponse({
            "jaccard": hyper_minhash.jaccard(other),
            "union": hyper_minhash.union_cardinality(other),
            "intersection": hyper_minhash.intersection_cardinality(other),
        })

    @app.get("/api/v1/hyperminhash/stats")
    async def api_hmh_stats() -> JSONResponse:
        return JSONResponse(hyper_minhash.stats())

    @app.delete("/api/v1/hyperminhash/reset")
    async def api_hmh_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            hyper_minhash.reset(body.get("p"), body.get("r"), body.get("seed"))
        except HyperMinHashError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(hyper_minhash.stats())

    return hyper_minhash
