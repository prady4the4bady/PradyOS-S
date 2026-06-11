"""Phase 88 — Sovereign MinHash HTTP routes.

Exposes a :class:`~pradyos.core.minhash.MinHash` (a multi-set store) over REST.
Routes are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()``
via :func:`register_minhash_routes`, called *inside* the factory — the store lives
in factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

Where Phase 74's HyperLogLog estimates *cardinality* and Phases 76/87 estimate
*frequency*, this estimates set *similarity* — the Jaccard half of the sketch stack.

Routes (mounted under ``/api/v1/minhash``):
  POST /api/v1/minhash/add         body ``{"set": name, "element": x}`` / ``{"set": name, "elements": [...]}``
  GET  /api/v1/minhash/similarity  ``?a=NAME&b=NAME`` — estimated Jaccard of two stored sets
  GET  /api/v1/minhash/stats       ``{num_hashes, sets, total_added, seed}``
  POST /api/v1/minhash/reset       body ``{"num_hashes"?: int, "seed"?: int}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.minhash import MinHash, MinHashError

DEFAULT_NUM_HASHES = 128


def register_minhash_routes(app: Any, minhash: Any | None = None) -> Any:
    """Register the /api/v1/minhash routes on ``app``; return the store used.

    ``minhash`` defaults to a fresh :class:`MinHash` owned by this app instance
    (factory scope — never a module-level global)."""
    if minhash is None:
        minhash = MinHash(DEFAULT_NUM_HASHES)

    @app.post("/api/v1/minhash/add")
    async def api_minhash_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "set" not in body:
            return JSONResponse({"error": "set is required"}, status_code=422)
        name = body["set"]
        if "elements" in body:
            elements = body.get("elements")
            if not isinstance(elements, list):
                return JSONResponse({"error": "elements must be a list"}, status_code=422)
            added = minhash.add_many(name, elements)
        elif "element" in body:
            minhash.add(name, body.get("element"))
            added = 1
        else:
            return JSONResponse({"error": "element or elements is required"}, status_code=422)
        return JSONResponse({"set": str(name), "added": added, "sets": len(minhash)})

    @app.get("/api/v1/minhash/similarity")
    async def api_minhash_similarity(a: str, b: str) -> JSONResponse:
        return JSONResponse({"a": a, "b": b, "similarity": minhash.similarity(a, b)})

    @app.get("/api/v1/minhash/stats")
    async def api_minhash_stats() -> JSONResponse:
        return JSONResponse(minhash.stats())

    @app.post("/api/v1/minhash/reset")
    async def api_minhash_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        num_hashes = body.get("num_hashes") if isinstance(body, dict) else None
        seed = body.get("seed") if isinstance(body, dict) else None
        try:
            minhash.reset(num_hashes, seed)
        except MinHashError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(minhash.stats())

    return minhash
