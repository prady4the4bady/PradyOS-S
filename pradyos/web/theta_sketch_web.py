"""Phase 93 — Sovereign Theta Sketch HTTP routes.

Exposes a :class:`~pradyos.core.theta_sketch.ThetaSketch` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_theta_sketch_routes`, called *inside* the factory — the sketch
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Like Phase 74's HyperLogLog this estimates distinct-count, but via K-Minimum-Values,
which supports a lossless set **union** (``op=union``) and an inclusion–exclusion
**intersection** (``op=intersection``) over the ``/merge`` route.

Routes (mounted under ``/api/v1/theta``):
  POST /api/v1/theta/insert    body ``{"element": x}`` or ``{"elements": [...]}``
  GET  /api/v1/theta/estimate  ``{estimate, n, is_exact}`` (0 when empty)
  POST /api/v1/theta/merge     ``?op=union|intersection`` body ``{"values": [...]}``
  GET  /api/v1/theta/stats     ``{k, n, theta, retained_count, is_exact, estimate}``
  POST /api/v1/theta/reset     body ``{"k"?: int, "seed"?: int}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.theta_sketch import ThetaError, ThetaSketch

DEFAULT_K = 4096


def register_theta_sketch_routes(app: Any, theta: Any | None = None) -> Any:
    """Register the /api/v1/theta routes on ``app``; return the sketch used.

    ``theta`` defaults to a fresh :class:`ThetaSketch` owned by this app instance
    (factory scope — never a module-level global)."""
    if theta is None:
        theta = ThetaSketch(DEFAULT_K)

    @app.post("/api/v1/theta/insert")
    async def api_theta_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "element or elements is required"}, status_code=422)
        if "elements" in body:
            elements = body.get("elements")
            if not isinstance(elements, list):
                return JSONResponse({"error": "elements must be a list"}, status_code=422)
            added = theta.update_many(elements)
        elif "element" in body:
            theta.update(body.get("element"))
            added = 1
        else:
            return JSONResponse({"error": "element or elements is required"}, status_code=422)
        return JSONResponse({"inserted": added, "n": len(theta), "estimate": theta.estimate()})

    @app.get("/api/v1/theta/estimate")
    async def api_theta_estimate() -> JSONResponse:
        return JSONResponse(
            {"estimate": theta.estimate(), "n": len(theta), "is_exact": theta.is_exact}
        )

    @app.post("/api/v1/theta/merge")
    async def api_theta_merge(request: Request, op: str = Query("union")) -> JSONResponse:
        if op not in ("union", "intersection"):
            return JSONResponse({"error": "op must be 'union' or 'intersection'"}, status_code=422)
        body = await request.json()
        if not isinstance(body, dict) or "values" not in body:
            return JSONResponse({"error": "values is required"}, status_code=422)
        values = body.get("values")
        if not isinstance(values, list):
            return JSONResponse({"error": "values must be a list"}, status_code=422)
        other = ThetaSketch(k=theta.k, seed=theta.seed)
        other.update_many(values)
        if op == "union":
            theta.merge(other)  # folds the batch in (mutating)
            return JSONResponse({"op": op, "estimate": theta.estimate(), "n": len(theta)})
        estimate = theta.intersection_estimate(other)  # non-destructive
        return JSONResponse({"op": op, "estimate": estimate})

    @app.get("/api/v1/theta/stats")
    async def api_theta_stats() -> JSONResponse:
        return JSONResponse(theta.stats())

    @app.post("/api/v1/theta/reset")
    async def api_theta_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            theta.reset(body.get("k"), body.get("seed"))
        except ThetaError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(theta.stats())

    return theta
