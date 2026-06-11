"""Phase 110 — Sovereign Stable Bloom Filter HTTP routes.

Exposes a :class:`~pradyos.core.stable_bloom.StableBloomFilter` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_stablebloom_routes`, called *inside* the factory — the filter lives
in factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

There is **no remove** route — the Stable Bloom Filter forgets old elements on its
own (every ``add`` evicts ``P`` random cells), so deletion is implicit; ``reset``
clears or reconfigures the whole filter.

Routes (mounted under ``/api/v1/stablebloom``):
  POST   /api/v1/stablebloom/add       body ``{"element": x}`` — add an element
  GET    /api/v1/stablebloom/contains  ``?element=`` — membership test
  GET    /api/v1/stablebloom/stats     ``{num_cells, num_hashes, max_value, decrement, count, fill_ratio, seed}``
  DELETE /api/v1/stablebloom/reset     body ``{"num_cells"?, "num_hashes"?, "max_value"?, "decrement"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.stable_bloom import StableBloomError, StableBloomFilter


def register_stablebloom_routes(app: Any, stable_bloom: Any | None = None) -> Any:
    """Register the /api/v1/stablebloom routes on ``app``; return the filter used.

    ``stable_bloom`` defaults to a fresh :class:`StableBloomFilter` owned by this app
    instance (factory scope — never a module-level global)."""
    if stable_bloom is None:
        stable_bloom = StableBloomFilter()

    @app.post("/api/v1/stablebloom/add")
    async def api_sbf_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "element" not in body:
            return JSONResponse({"error": "element is required"}, status_code=422)
        stable_bloom.add(str(body["element"]))
        return JSONResponse({"element": str(body["element"]), "count": stable_bloom.count})

    @app.get("/api/v1/stablebloom/contains")
    async def api_sbf_contains(element: str) -> JSONResponse:
        return JSONResponse({"element": element, "contains": stable_bloom.contains(element)})

    @app.get("/api/v1/stablebloom/stats")
    async def api_sbf_stats() -> JSONResponse:
        return JSONResponse(stable_bloom.stats())

    @app.delete("/api/v1/stablebloom/reset")
    async def api_sbf_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            stable_bloom.reset(
                body.get("num_cells"),
                body.get("num_hashes"),
                body.get("max_value"),
                body.get("decrement"),
                body.get("seed"),
            )
        except StableBloomError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(stable_bloom.stats())

    return stable_bloom
