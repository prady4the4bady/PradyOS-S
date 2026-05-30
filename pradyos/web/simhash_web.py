"""Phase 89 — Sovereign SimHash HTTP routes.

Exposes a :class:`~pradyos.core.simhash.SimHash` (a multi-document store) over
REST. Routes are registered onto the FastAPI ``app`` built by
``sovereign_web.create_app()`` via :func:`register_simhash_routes`, called
*inside* the factory — the store lives in factory scope (passed in, or created
fresh per app), so there is no module-level singleton. All routes are static (no
path parameters), so none can shadow another.

Where Phase 88's MinHash estimates *Jaccard* (set) similarity, SimHash estimates
*Hamming* (bit-fingerprint) similarity — the near-duplicate-detection sketch.

Routes (mounted under ``/api/v1/simhash``):
  POST /api/v1/simhash/hash        body ``{"doc": name, "tokens": [...]}`` — store a fingerprint
  GET  /api/v1/simhash/similarity  ``?a=NAME&b=NAME`` — normalized 1 − hamming/num_bits
  GET  /api/v1/simhash/hamming     ``?a=NAME&b=NAME`` — raw bit distance
  GET  /api/v1/simhash/stats       ``{num_bits, docs, total_hashed, seed}``
  POST /api/v1/simhash/reset       body ``{"num_bits"?: int, "seed"?: int}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.simhash import NEAR_DUPLICATE_HAMMING, SimHash, SimHashError

DEFAULT_NUM_BITS = 64


def register_simhash_routes(app: Any, simhash: Any | None = None) -> Any:
    """Register the /api/v1/simhash routes on ``app``; return the store used.

    ``simhash`` defaults to a fresh :class:`SimHash` owned by this app instance
    (factory scope — never a module-level global)."""
    if simhash is None:
        simhash = SimHash(DEFAULT_NUM_BITS)

    @app.post("/api/v1/simhash/hash")
    async def api_simhash_hash(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "doc" not in body:
            return JSONResponse({"error": "doc is required"}, status_code=422)
        tokens = body.get("tokens")
        if not isinstance(tokens, list):
            return JSONResponse({"error": "tokens must be a list"}, status_code=422)
        fp = simhash.hash(body["doc"], tokens)
        return JSONResponse({"doc": str(body["doc"]), "fingerprint": fp, "docs": len(simhash)})

    @app.get("/api/v1/simhash/similarity")
    async def api_simhash_similarity(a: str, b: str) -> JSONResponse:
        sim = simhash.similarity(a, b)
        if sim is None:
            return JSONResponse({"error": "unknown document"}, status_code=404)
        return JSONResponse({"a": a, "b": b, "similarity": sim})

    @app.get("/api/v1/simhash/hamming")
    async def api_simhash_hamming(a: str, b: str) -> JSONResponse:
        dist = simhash.hamming(a, b)
        if dist is None:
            return JSONResponse({"error": "unknown document"}, status_code=404)
        return JSONResponse({
            "a": a, "b": b, "hamming": dist,
            "near_duplicate": dist <= NEAR_DUPLICATE_HAMMING,
        })

    @app.get("/api/v1/simhash/stats")
    async def api_simhash_stats() -> JSONResponse:
        return JSONResponse(simhash.stats())

    @app.post("/api/v1/simhash/reset")
    async def api_simhash_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        num_bits = body.get("num_bits") if isinstance(body, dict) else None
        seed = body.get("seed") if isinstance(body, dict) else None
        try:
            simhash.reset(num_bits, seed)
        except SimHashError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(simhash.stats())

    return simhash
