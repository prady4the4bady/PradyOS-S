"""Sovereign Experience Distribution HTTP routes (cognitive layer).

Exposes an :class:`~pradyos.core.experience_distribution.ExperienceDistribution`
over REST. Registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()``
via :func:`register_experience_routes`, called *inside* the factory — the tracker
lives in factory scope (no module-level singleton).

Routes (mounted under ``/api/v1/experience``):
  POST   /api/v1/experience/observe     body ``{"metric","value"}`` — record an observation
  GET    /api/v1/experience/percentile  ``?metric=&q=`` — q-th percentile (q in (0,1))
  GET    /api/v1/experience/anomaly      ``?metric=&value=`` — robust IQR anomaly score
  GET    /api/v1/experience/summary      ``?metric=`` — {min,p25,p50,p75,p90,p99,max,count}
  GET    /api/v1/experience/metrics      — list tracked metric names
  POST   /api/v1/experience/reset        clear all metrics
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.experience_distribution import (
    ExperienceDistribution,
    ExperienceDistributionError,
)


def register_experience_routes(app: Any, tracker: Any | None = None) -> Any:
    """Register the /api/v1/experience routes on ``app``; return the tracker used."""
    if tracker is None:
        tracker = ExperienceDistribution()

    @app.post("/api/v1/experience/observe")
    async def api_exp_observe(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "metric" not in body or "value" not in body:
            return JSONResponse({"error": "metric and value are required"}, status_code=422)
        try:
            tracker.observe(str(body["metric"]), body["value"])
        except ExperienceDistributionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"metric": body["metric"], "metrics": tracker.stats()["num_metrics"]})

    @app.get("/api/v1/experience/percentile")
    async def api_exp_percentile(metric: str = Query(...), q: float = Query(..., gt=0.0, lt=1.0)) -> JSONResponse:
        try:
            return JSONResponse({"metric": metric, "q": q, "value": tracker.percentile(metric, q)})
        except ExperienceDistributionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @app.get("/api/v1/experience/anomaly")
    async def api_exp_anomaly(metric: str = Query(...), value: float = Query(...)) -> JSONResponse:
        try:
            return JSONResponse({"metric": metric, "value": value, "anomaly_score": tracker.anomaly_score(metric, value)})
        except ExperienceDistributionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @app.get("/api/v1/experience/summary")
    async def api_exp_summary(metric: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(tracker.distribution_summary(metric))
        except ExperienceDistributionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @app.get("/api/v1/experience/metrics")
    async def api_exp_metrics() -> JSONResponse:
        return JSONResponse({"metrics": tracker.list_metrics(), "stats": tracker.stats()})

    @app.post("/api/v1/experience/reset")
    async def api_exp_reset() -> JSONResponse:
        tracker.reset()
        return JSONResponse(tracker.stats())

    return tracker
