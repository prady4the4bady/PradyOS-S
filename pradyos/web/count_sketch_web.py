"""Phase 94 — Sovereign Count Sketch HTTP routes.

Exposes a :class:`~pradyos.core.count_sketch.CountSketch` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_count_sketch_routes`, called *inside* the factory — the sketch
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Like Phase 76's Count-Min Sketch this estimates item frequencies, but via signed
hashes and a median estimator — so it is **unbiased**, supports **deletion**
(negative ``count``), and can report small negative estimates for never-seen
items that collide with negative updates (the expected trade-off for unbiasedness).
Elements are normalised to strings for transport consistency.

Routes (mounted under ``/api/v1/countsketch``):
  POST /api/v1/countsketch/update         ``?count=N`` body ``{"element": x}`` / ``{"elements": [...]}``
  GET  /api/v1/countsketch/estimate       ``?element=x`` — signed-median estimate
  GET  /api/v1/countsketch/heavy_hitters   ``?threshold=0.01`` — items above threshold·total
  GET  /api/v1/countsketch/stats          ``{depth, width, total_count, unique_elements, table_cells}``
  POST /api/v1/countsketch/reset          body ``{"depth"?, "width"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.count_sketch import CountSketch, CountSketchError

DEFAULT_DEPTH = 5
DEFAULT_WIDTH = 2048


def register_count_sketch_routes(app: Any, count_sketch: Any | None = None) -> Any:
    """Register the /api/v1/countsketch routes on ``app``; return the sketch used.

    ``count_sketch`` defaults to a fresh :class:`CountSketch` owned by this app
    instance (factory scope — never a module-level global)."""
    if count_sketch is None:
        count_sketch = CountSketch(DEFAULT_DEPTH, DEFAULT_WIDTH)

    @app.post("/api/v1/countsketch/update")
    async def api_cs_update(request: Request, count: int = Query(default=1)) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "element or elements is required"}, status_code=422)
        if "elements" in body:
            elements = body.get("elements")
            if not isinstance(elements, list):
                return JSONResponse({"error": "elements must be a list"}, status_code=422)
            for element in elements:
                count_sketch.update(str(element), count)
            updated = len(elements)
        elif "element" in body:
            count_sketch.update(str(body.get("element")), count)
            updated = 1
        else:
            return JSONResponse({"error": "element or elements is required"}, status_code=422)
        return JSONResponse({"updated": updated, "total_count": count_sketch.total_count})

    @app.get("/api/v1/countsketch/estimate")
    async def api_cs_estimate(element: str) -> JSONResponse:
        return JSONResponse({"element": element, "estimate": count_sketch.estimate(element)})

    @app.get("/api/v1/countsketch/heavy_hitters")
    async def api_cs_heavy_hitters(threshold: float = Query(ge=0.0, le=1.0)) -> JSONResponse:
        return JSONResponse({"threshold": threshold,
                             "heavy_hitters": count_sketch.heavy_hitters(threshold)})

    @app.get("/api/v1/countsketch/stats")
    async def api_cs_stats() -> JSONResponse:
        return JSONResponse(count_sketch.stats())

    @app.post("/api/v1/countsketch/reset")
    async def api_cs_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            count_sketch.reset(body.get("depth"), body.get("width"), body.get("seed"))
        except CountSketchError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(count_sketch.stats())

    return count_sketch
