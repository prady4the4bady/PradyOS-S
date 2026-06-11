"""Phase 98 — Sovereign Weighted Reservoir Sampling HTTP routes.

Exposes a :class:`~pradyos.core.weighted_reservoir.WeightedReservoir` over REST.
Routes are registered onto the FastAPI ``app`` built by
``sovereign_web.create_app()`` via :func:`register_weighted_reservoir_routes`,
called *inside* the factory — the sampler lives in factory scope (passed in, or
created fresh per app), so there is no module-level singleton. All routes are
static (no path parameters), so none can shadow another.

Where Phase 85's reservoir samples *uniformly* (Vitter's Algorithm R), this samples
**proportionally to weight** (Efraimidis–Spirakis A-Res). There is no merge route —
A-Res reservoirs are not composable. Items are normalised to strings for transport.

Routes (mounted under ``/api/v1/sample``):
  POST /api/v1/sample/update   ``?item=x&weight=W`` (weight > 0) — observe one item
  GET  /api/v1/sample/sample   ``{items, n, k}`` — current reservoir contents
  GET  /api/v1/sample/stats    ``{k, n, size, seed}``
  POST /api/v1/sample/reset    clear the reservoir (the RNG state continues)
"""

from __future__ import annotations

from typing import Any

from fastapi import Query
from fastapi.responses import JSONResponse

from pradyos.core.weighted_reservoir import WeightedReservoir

DEFAULT_K = 100


def register_weighted_reservoir_routes(app: Any, reservoir: Any | None = None) -> Any:
    """Register the /api/v1/sample routes on ``app``; return the sampler used.

    ``reservoir`` defaults to a fresh :class:`WeightedReservoir` owned by this app
    instance (factory scope — never a module-level global)."""
    if reservoir is None:
        reservoir = WeightedReservoir(DEFAULT_K)

    @app.post("/api/v1/sample/update")
    async def api_sample_update(
        item: str, weight: float = Query(default=1.0, gt=0.0)
    ) -> JSONResponse:
        reservoir.update(str(item), weight)
        return JSONResponse(
            {"item": str(item), "weight": weight, "n": reservoir.n, "size": reservoir.size}
        )

    @app.get("/api/v1/sample/sample")
    async def api_sample_sample() -> JSONResponse:
        return JSONResponse({"items": reservoir.sample(), "n": reservoir.n, "k": reservoir.k})

    @app.get("/api/v1/sample/stats")
    async def api_sample_stats() -> JSONResponse:
        return JSONResponse(reservoir.stats())

    @app.post("/api/v1/sample/reset")
    async def api_sample_reset() -> JSONResponse:
        reservoir.reset()
        return JSONResponse(reservoir.stats())

    return reservoir
