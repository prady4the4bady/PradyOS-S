"""Phase 112 — Sovereign Linear Counting HTTP routes.

Exposes a :class:`~pradyos.core.linear_counter.LinearCounter` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_linearcounting_routes`, called *inside* the factory — the counter
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

A **saturated** bitmap (every bit set) has no defined cardinality estimate, so
``GET /estimate`` surfaces that as **HTTP 400** (a state error, distinct from the
422 used for request-shape validation); ``GET /stats`` reports ``estimate: null``.

Routes (mounted under ``/api/v1/linearcounting``):
  POST   /api/v1/linearcounting/add       body ``{"element": x}`` — add an item
  GET    /api/v1/linearcounting/estimate  ``{estimate, bits_set}`` — distinct-count estimate; 400 if saturated
  GET    /api/v1/linearcounting/stats     ``{num_bits, bits_set, zero_bits, load_factor, estimate, seed}``
  DELETE /api/v1/linearcounting/reset     body ``{"num_bits"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.linear_counter import LinearCounter, LinearCounterError


def register_linearcounting_routes(app: Any, linear_counter: Any | None = None) -> Any:
    """Register the /api/v1/linearcounting routes on ``app``; return the counter used.

    ``linear_counter`` defaults to a fresh :class:`LinearCounter` owned by this app
    instance (factory scope — never a module-level global)."""
    if linear_counter is None:
        linear_counter = LinearCounter()

    @app.post("/api/v1/linearcounting/add")
    async def api_lc_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "element" not in body:
            return JSONResponse({"error": "element is required"}, status_code=422)
        linear_counter.add(str(body["element"]))
        return JSONResponse({"element": str(body["element"]), "bits_set": linear_counter.bits_set})

    @app.get("/api/v1/linearcounting/estimate")
    async def api_lc_estimate() -> JSONResponse:
        try:
            est = linear_counter.estimate()
        except LinearCounterError as exc:
            # saturated bitmap → estimate undefined; a state error, not a 422.
            return JSONResponse({"error": str(exc.detail)}, status_code=400)
        return JSONResponse({"estimate": est, "bits_set": linear_counter.bits_set})

    @app.get("/api/v1/linearcounting/stats")
    async def api_lc_stats() -> JSONResponse:
        return JSONResponse(linear_counter.stats())

    @app.delete("/api/v1/linearcounting/reset")
    async def api_lc_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            linear_counter.reset(body.get("num_bits"), body.get("seed"))
        except LinearCounterError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(linear_counter.stats())

    return linear_counter
