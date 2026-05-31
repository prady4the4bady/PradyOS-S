"""Phase 103 — Sovereign Spectral Bloom Filter HTTP routes.

Exposes a :class:`~pradyos.core.spectral_bloom.SpectralBloom` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()``
via :func:`register_spectralbloom_routes`, called *inside* the factory — the
filter lives in factory scope (passed in, or created fresh per app), so there is
no module-level singleton. All routes are static (no path parameters), so none
can shadow another. Items are normalised to strings for transport.

Unlike the standard membership Bloom (P12), the spectral filter answers *how
many* (min counter across the ``k`` positions) and — because its cells are
counters — supports **deletion** via ``remove`` (exposed as ``DELETE`` with a
body, mirroring REST delete semantics).

Routes (mounted under ``/api/v1/spectralbloom``):
  POST   /api/v1/spectralbloom/add     body ``{"item": x, "count"?: c}`` — add occurrences
  GET    /api/v1/spectralbloom/query   ``?item=x`` — multiplicity estimate (min counter)
  DELETE /api/v1/spectralbloom/remove  body ``{"item": x, "count"?: c}`` — delete occurrences
  GET    /api/v1/spectralbloom/stats   ``{capacity, error_rate, num_bits, num_hashes, ...}``
  POST   /api/v1/spectralbloom/reset   body ``{"capacity"?, "error_rate"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.spectral_bloom import SpectralBloom, SpectralBloomError


def register_spectralbloom_routes(app: Any, spectral: Any | None = None) -> Any:
    """Register the /api/v1/spectralbloom routes on ``app``; return the filter used.

    ``spectral`` defaults to a fresh :class:`SpectralBloom` owned by this app
    instance (factory scope — never a module-level global)."""
    if spectral is None:
        spectral = SpectralBloom()

    @app.post("/api/v1/spectralbloom/add")
    async def api_sb_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        try:
            estimate = spectral.add(str(body["item"]), body.get("count", 1))
        except SpectralBloomError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"item": str(body["item"]), "count": body.get("count", 1),
                             "estimate": estimate})

    @app.get("/api/v1/spectralbloom/query")
    async def api_sb_query(item: str) -> JSONResponse:
        return JSONResponse({"item": item, "count": spectral.query(item)})

    @app.delete("/api/v1/spectralbloom/remove")
    async def api_sb_remove(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        try:
            removed = spectral.remove(str(body["item"]), body.get("count", 1))
        except SpectralBloomError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"item": str(body["item"]), "removed": removed,
                             "estimate": spectral.query(str(body["item"]))})

    @app.get("/api/v1/spectralbloom/stats")
    async def api_sb_stats() -> JSONResponse:
        return JSONResponse(spectral.stats())

    @app.post("/api/v1/spectralbloom/reset")
    async def api_sb_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            spectral.reset(body.get("capacity"), body.get("error_rate"), body.get("seed"))
        except SpectralBloomError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(spectral.stats())

    return spectral
