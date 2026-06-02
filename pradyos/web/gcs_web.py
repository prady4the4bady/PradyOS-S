"""Phase 128 — Sovereign Golomb-Coded Set HTTP routes.

Exposes a :class:`~pradyos.core.golomb_coded_set.GolombCodedSet` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_gcs_routes`, called *inside* the factory — the set lives in factory scope
(passed in, or created fresh per app), so there is no module-level singleton. All routes are
static (no path parameters), so none can shadow another.

An out-of-range / wrong-type item or configuration is a request error → **HTTP 422**.

Routes (mounted under ``/api/v1/gcs``):
  POST   /api/v1/gcs/build         body ``{"items": [...], "p"?, "seed"?}`` — (re)build, return stats
  POST   /api/v1/gcs/contains      body ``{"item": ...}`` — ``{item, contains}``
  POST   /api/v1/gcs/contains_many body ``{"items": [...]}`` — ``{results: [...], count}``
  GET    /api/v1/gcs/stats          ``{p, num_items, universe, golomb_m, num_bits, bits_per_item, seed}``
  DELETE /api/v1/gcs/reset          body ``{"p"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.golomb_coded_set import GolombCodedSet, GolombCodedSetError


def register_gcs_routes(app: Any, gcs: Any | None = None) -> Any:
    """Register the /api/v1/gcs routes on ``app``; return the set used.

    ``gcs`` defaults to a fresh :class:`GolombCodedSet` owned by this app instance
    (factory scope — never a module-level global)."""
    if gcs is None:
        gcs = GolombCodedSet()

    @app.post("/api/v1/gcs/build")
    async def api_gcs_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            return JSONResponse({"error": "items list is required"}, status_code=422)
        try:
            if "p" in body or "seed" in body:
                gcs.reset(body.get("p"), body.get("seed"))   # reconfigure (validates) + clear
            gcs.build(body["items"])
        except GolombCodedSetError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(gcs.stats())

    @app.post("/api/v1/gcs/contains")
    async def api_gcs_contains(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        try:
            present = gcs.contains(body["item"])
        except GolombCodedSetError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"item": body["item"], "contains": present})

    @app.post("/api/v1/gcs/contains_many")
    async def api_gcs_contains_many(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            return JSONResponse({"error": "items list is required"}, status_code=422)
        try:
            results = [gcs.contains(it) for it in body["items"]]
        except GolombCodedSetError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"results": results, "count": sum(results)})

    @app.get("/api/v1/gcs/stats")
    async def api_gcs_stats() -> JSONResponse:
        return JSONResponse(gcs.stats())

    @app.delete("/api/v1/gcs/reset")
    async def api_gcs_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            gcs.reset(body.get("p"), body.get("seed"))
        except GolombCodedSetError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(gcs.stats())

    return gcs
