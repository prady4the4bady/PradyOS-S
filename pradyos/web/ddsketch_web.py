"""Phase 96 — Sovereign DDSketch HTTP routes.

Exposes a :class:`~pradyos.core.ddsketch.DDSketch` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_ddsketch_routes`, called *inside* the factory — the sketch lives
in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Like Phases 91/92 this estimates quantiles, but with a **relative**-error
guarantee (``|v̂−v|/v ≤ α``) rather than rank error — and its **merge** is exact
(an addition of per-bucket counts), the basis for distributed quantile estimation.

**Merge pattern:** the server holds a single shared sketch, so (unlike a named
multi-sketch registry) ``/merge`` accepts a ``{"values": [...]}`` payload, builds
a temporary :class:`DDSketch` with the same ``α``, and folds it into the shared
sketch — demonstrating exact composability.

Routes (mounted under ``/api/v1/ddsketch``):
  POST /api/v1/ddsketch/update    ``?value=V&count=N`` (value>0) or body ``{"values": [...]}``
  GET  /api/v1/ddsketch/quantile  ``?q=0.99`` — the φ-quantile (422 if empty / q∉[0,1])
  POST /api/v1/ddsketch/merge     body ``{"values": [...]}`` — build a sketch and merge it in
  GET  /api/v1/ddsketch/stats     ``{alpha, gamma, n, num_buckets, min, max}``
  POST /api/v1/ddsketch/reset     body ``{"alpha"?: float}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.ddsketch import DDSketch, DDSketchError

DEFAULT_ALPHA = 0.01


def register_ddsketch_routes(app: Any, ddsketch: Any | None = None) -> Any:
    """Register the /api/v1/ddsketch routes on ``app``; return the sketch used.

    ``ddsketch`` defaults to a fresh :class:`DDSketch` owned by this app instance
    (factory scope — never a module-level global)."""
    if ddsketch is None:
        ddsketch = DDSketch(DEFAULT_ALPHA)

    @app.post("/api/v1/ddsketch/update")
    async def api_dd_update(
        request: Request,
        value: float | None = Query(default=None, gt=0.0),
        count: int = Query(default=1, ge=1),
    ) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict) and "values" in body:
            values = body.get("values")
            if not isinstance(values, list):
                return JSONResponse({"error": "values must be a list"}, status_code=422)
            try:
                for v in values:
                    ddsketch.update(v, count)
            except DDSketchError:
                return JSONResponse({"error": "DDSketch requires positive values"}, status_code=422)
            return JSONResponse({"updated": len(values), "n": ddsketch.count()})
        if value is not None:
            ddsketch.update(value, count)  # value already > 0 via Query(gt=0)
            return JSONResponse({"updated": 1, "n": ddsketch.count()})
        return JSONResponse({"error": "value or values is required"}, status_code=422)

    @app.get("/api/v1/ddsketch/quantile")
    async def api_dd_quantile(q: float = Query(ge=0.0, le=1.0)) -> JSONResponse:
        value = ddsketch.quantile(q)
        if value is None:
            return JSONResponse({"error": "sketch is empty"}, status_code=422)
        return JSONResponse({"q": q, "quantile": value, "n": ddsketch.count()})

    @app.post("/api/v1/ddsketch/merge")
    async def api_dd_merge(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "values" not in body:
            return JSONResponse({"error": "values is required"}, status_code=422)
        values = body.get("values")
        if not isinstance(values, list):
            return JSONResponse({"error": "values must be a list"}, status_code=422)
        try:
            other = DDSketch(alpha=ddsketch.alpha)
            for v in values:
                other.update(v)
        except DDSketchError:
            return JSONResponse({"error": "DDSketch requires positive values"}, status_code=422)
        ddsketch.merge(other)
        return JSONResponse({"merged": len(values), "n": ddsketch.count()})

    @app.get("/api/v1/ddsketch/stats")
    async def api_dd_stats() -> JSONResponse:
        return JSONResponse(ddsketch.stats())

    @app.post("/api/v1/ddsketch/reset")
    async def api_dd_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            ddsketch.reset(body.get("alpha"), body.get("seed"))
        except DDSketchError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(ddsketch.stats())

    return ddsketch
