"""Phase 131 — Sovereign Priority Sampling HTTP routes.

Exposes a :class:`~pradyos.core.priority_sampling.PrioritySample` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_prioritysample_routes`, called *inside* the factory — the sample lives in
factory scope (passed in, or created fresh per app), so there is no module-level singleton.
All routes are static (no path parameters), so none can shadow another.

A non-positive / wrong-type weight, bad key/category, or bad configuration is a request error
→ **HTTP 422**.

Routes (mounted under ``/api/v1/prioritysample``):
  POST   /api/v1/prioritysample/add       body ``{"key", "weight", "category"?}`` — ``{key, sampled, total_estimate}``
  POST   /api/v1/prioritysample/add_many  body ``{"items": [[key, weight(, category)], ...]}`` — ``{added, total_estimate}``
  GET    /api/v1/prioritysample/estimate  query ``?category=`` — ``{category, estimate}``
  GET    /api/v1/prioritysample/stats      ``{capacity, sampled, num_seen, threshold, total_estimate, seed}``
  DELETE /api/v1/prioritysample/reset      body ``{"capacity"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.priority_sampling import PrioritySample, PrioritySampleError


def register_prioritysample_routes(app: Any, priority_sample: Any | None = None) -> Any:
    """Register the /api/v1/prioritysample routes on ``app``; return the sample used.

    ``priority_sample`` defaults to a fresh :class:`PrioritySample` owned by this app instance
    (factory scope — never a module-level global)."""
    if priority_sample is None:
        priority_sample = PrioritySample()

    @app.post("/api/v1/prioritysample/add")
    async def api_ps_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body or "weight" not in body:
            return JSONResponse({"error": "key and weight are required"}, status_code=422)
        try:
            sampled = priority_sample.add(body["key"], body["weight"], body.get("category"))
        except PrioritySampleError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"key": body["key"], "sampled": sampled,
                             "total_estimate": priority_sample.stats()["total_estimate"]})

    @app.post("/api/v1/prioritysample/add_many")
    async def api_ps_add_many(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            return JSONResponse({"error": "items list is required"}, status_code=422)
        try:
            added = priority_sample.add_many(body["items"])
        except PrioritySampleError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"added": added,
                             "total_estimate": priority_sample.stats()["total_estimate"]})

    @app.get("/api/v1/prioritysample/estimate")
    async def api_ps_estimate(category: str | None = None) -> JSONResponse:
        try:
            est = priority_sample.estimate(category)
        except PrioritySampleError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"category": category, "estimate": round(est, 4)})

    @app.get("/api/v1/prioritysample/stats")
    async def api_ps_stats() -> JSONResponse:
        return JSONResponse(priority_sample.stats())

    @app.delete("/api/v1/prioritysample/reset")
    async def api_ps_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            priority_sample.reset(body.get("capacity"), body.get("seed"))
        except PrioritySampleError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(priority_sample.stats())

    return priority_sample
