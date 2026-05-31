"""Phase 97 — Sovereign Exponential Histogram HTTP routes.

Exposes an :class:`~pradyos.core.exponential_histogram.ExponentialHistogram` over
REST. Routes are registered onto the FastAPI ``app`` built by
``sovereign_web.create_app()`` via :func:`register_exponential_histogram_routes`,
called *inside* the factory — the histogram lives in factory scope (passed in, or
created fresh per app), so there is no module-level singleton. All routes are
static (no path parameters), so none can shadow another.

This is the first **sliding-window** primitive: it answers "how many 1-bits in
the last ``window`` ticks?" with `(1 ± ε/2)` accuracy — a recency dimension none
of the unbounded-stream sketches (P74–P96) address.

Routes (mounted under ``/api/v1/window``):
  POST /api/v1/window/update   ``?value=N&timestamp=T`` — record N 1-bits at a tick
  GET  /api/v1/window/count    ``{count, now}`` — DGIM windowed count estimate
  GET  /api/v1/window/oldest   ``{oldest}`` — timestamp of the oldest surviving bucket
  GET  /api/v1/window/stats    ``{window, epsilon, k, num_buckets, count, oldest, now}``
  POST /api/v1/window/reset    ``?window=W&epsilon=E`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query
from fastapi.responses import JSONResponse

from pradyos.core.exponential_histogram import (
    ExponentialHistogram,
    ExponentialHistogramError,
)

DEFAULT_WINDOW = 1000


def register_exponential_histogram_routes(app: Any, histogram: Any | None = None) -> Any:
    """Register the /api/v1/window routes on ``app``; return the histogram used.

    ``histogram`` defaults to a fresh :class:`ExponentialHistogram` owned by this
    app instance (factory scope — never a module-level global)."""
    if histogram is None:
        histogram = ExponentialHistogram(DEFAULT_WINDOW)

    @app.post("/api/v1/window/update")
    async def api_window_update(value: int = Query(default=1, ge=1),
                                timestamp: int | None = Query(default=None, ge=0)) -> JSONResponse:
        try:
            histogram.update(value, timestamp)
        except ExponentialHistogramError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"now": histogram.now, "count": histogram.count(),
                             "num_buckets": histogram.num_buckets})

    @app.get("/api/v1/window/count")
    async def api_window_count() -> JSONResponse:
        return JSONResponse({"count": histogram.count(), "now": histogram.now})

    @app.get("/api/v1/window/oldest")
    async def api_window_oldest() -> JSONResponse:
        return JSONResponse({"oldest": histogram.oldest()})

    @app.get("/api/v1/window/stats")
    async def api_window_stats() -> JSONResponse:
        return JSONResponse(histogram.stats())

    @app.post("/api/v1/window/reset")
    async def api_window_reset(window: int | None = Query(default=None, gt=0),
                               epsilon: float | None = Query(default=None, gt=0.0, le=1.0)) -> JSONResponse:
        try:
            histogram.reset(window, epsilon)
        except ExponentialHistogramError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(histogram.stats())

    return histogram
