"""Phase 122 — Sovereign b-bit MinHash HTTP routes.

Exposes a :class:`~pradyos.core.bbit_minhash.BBitMinHash` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_bbitminhash_routes`, called *inside* the factory — the sketch lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

The app holds one *primary* sketch (add / signature / stats / reset). ``POST /compare``
builds a throwaway sketch from the request's ``tokens`` (using the primary's
``num_perm`` / ``b`` / ``seed`` so they are compatible) and returns the bias-corrected
Jaccard estimate against the primary.

Routes (mounted under ``/api/v1/bbitminhash``):
  POST   /api/v1/bbitminhash/add        body ``{"element": x}`` — fold an element in
  POST   /api/v1/bbitminhash/compare    body ``{"tokens": [...]}`` — ``{jaccard}`` vs primary
  GET    /api/v1/bbitminhash/signature  ``{signature, signature_bits}``
  GET    /api/v1/bbitminhash/stats      ``{num_perm, b, count, signature_bits, seed}``
  DELETE /api/v1/bbitminhash/reset      body ``{"num_perm"?, "b"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.bbit_minhash import BBitMinHash, BBitMinHashError


def register_bbitminhash_routes(app: Any, bbit_minhash: Any | None = None) -> Any:
    """Register the /api/v1/bbitminhash routes on ``app``; return the sketch used.

    ``bbit_minhash`` defaults to a fresh :class:`BBitMinHash` owned by this app instance
    (factory scope — never a module-level global)."""
    if bbit_minhash is None:
        bbit_minhash = BBitMinHash()

    @app.post("/api/v1/bbitminhash/add")
    async def api_bbit_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "element" not in body:
            return JSONResponse({"error": "element is required"}, status_code=422)
        bbit_minhash.add(body["element"])
        return JSONResponse({"element": body["element"], "count": bbit_minhash.count})

    @app.post("/api/v1/bbitminhash/compare")
    async def api_bbit_compare(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("tokens"), list):
            return JSONResponse({"error": "tokens list is required"}, status_code=422)
        other = BBitMinHash(
            num_perm=bbit_minhash.num_perm, b=bbit_minhash.b, seed=bbit_minhash.seed
        )
        other.add_many(body["tokens"])
        return JSONResponse({"jaccard": bbit_minhash.jaccard(other)})

    @app.get("/api/v1/bbitminhash/signature")
    async def api_bbit_signature() -> JSONResponse:
        return JSONResponse(
            {
                "signature": list(bbit_minhash.signature()),
                "signature_bits": bbit_minhash.signature_bits(),
            }
        )

    @app.get("/api/v1/bbitminhash/stats")
    async def api_bbit_stats() -> JSONResponse:
        return JSONResponse(bbit_minhash.stats())

    @app.delete("/api/v1/bbitminhash/reset")
    async def api_bbit_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            bbit_minhash.reset(body.get("num_perm"), body.get("b"), body.get("seed"))
        except BBitMinHashError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(bbit_minhash.stats())

    return bbit_minhash
