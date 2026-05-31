"""Phase 107 — Sovereign Counting Bloom Filter HTTP routes.

Exposes a :class:`~pradyos.core.counting_bloom.CountingBloom` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()``
via :func:`register_countingbloom_routes`, called *inside* the factory — the
filter lives in factory scope (passed in, or created fresh per app), so there is
no module-level singleton. All routes are static (no path parameters), so none
can shadow another.

Routes (mounted under ``/api/v1/countingbloom``):
  POST   /api/v1/countingbloom/add       body ``{"element": x}`` — add an element
  GET    /api/v1/countingbloom/contains  ``?element=`` — membership test
  POST   /api/v1/countingbloom/remove    body ``{"element": x}`` — delete; **400** if absent
  GET    /api/v1/countingbloom/stats     ``{capacity, error_rate, num_hash_functions, num_counters, count, false_positive_rate}``
  DELETE /api/v1/countingbloom/reset     body ``{"capacity"?, "error_rate"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.counting_bloom import CountingBloom, CountingBloomError


def register_countingbloom_routes(app: Any, counting_bloom: Any | None = None) -> Any:
    """Register the /api/v1/countingbloom routes on ``app``; return the filter used.

    ``counting_bloom`` defaults to a fresh :class:`CountingBloom` owned by this app
    instance (factory scope — never a module-level global)."""
    if counting_bloom is None:
        counting_bloom = CountingBloom()

    @app.post("/api/v1/countingbloom/add")
    async def api_cb_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "element" not in body:
            return JSONResponse({"error": "element is required"}, status_code=422)
        counting_bloom.add(str(body["element"]))
        return JSONResponse({"element": str(body["element"]), "count": counting_bloom.count})

    @app.get("/api/v1/countingbloom/contains")
    async def api_cb_contains(element: str) -> JSONResponse:
        return JSONResponse({"element": element, "contains": counting_bloom.contains(element)})

    @app.post("/api/v1/countingbloom/remove")
    async def api_cb_remove(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "element" not in body:
            return JSONResponse({"error": "element is required"}, status_code=422)
        try:
            counting_bloom.remove(str(body["element"]))
        except CountingBloomError as exc:
            # remove-of-absent is a client error about state, not a validation error → 400
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"element": str(body["element"]), "count": counting_bloom.count})

    @app.get("/api/v1/countingbloom/stats")
    async def api_cb_stats() -> JSONResponse:
        return JSONResponse(counting_bloom.stats())

    @app.delete("/api/v1/countingbloom/reset")
    async def api_cb_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            counting_bloom.reset(body.get("capacity"), body.get("error_rate"), body.get("seed"))
        except CountingBloomError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(counting_bloom.stats())

    return counting_bloom
