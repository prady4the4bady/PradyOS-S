"""Sovereign Novelty Detector HTTP routes (cognitive layer).

Exposes a :class:`~pradyos.core.novelty_detector.NoveltyDetector` over REST.
Routes are registered onto the FastAPI ``app`` built by
``sovereign_web.create_app()`` via :func:`register_novelty_detector_routes`,
called *inside* the factory — the detector lives in factory scope (passed in, or
created fresh per app), so there is no module-level singleton.

Routes (mounted under ``/api/v1/novelty``):
  POST   /api/v1/novelty/observe     body ``{"item": "..."}`` — record an observation
  GET    /api/v1/novelty/is_novel     ``?item=`` — is this item (probably) new?
  GET    /api/v1/novelty/rate         — overall novelty rate
  GET    /api/v1/novelty/surprise     ``?item=`` — surprise score for an item
  GET    /api/v1/novelty/stats        — detector statistics
  DELETE /api/v1/novelty/reset        clear all state
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.novelty_detector import NoveltyDetector, NoveltyDetectorError


def register_novelty_detector_routes(app: Any, detector: Any | None = None) -> Any:
    """Register the /api/v1/novelty routes on ``app``; return the detector used.

    ``detector`` defaults to a fresh :class:`NoveltyDetector` owned by this app
    instance (factory scope — never a module-level global)."""
    if detector is None:
        detector = NoveltyDetector()

    @app.post("/api/v1/novelty/observe")
    async def api_novelty_observe(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "item" not in body:
            return JSONResponse({"error": "item is required"}, status_code=422)
        try:
            detector.observe(str(body["item"]))
        except NoveltyDetectorError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"item": body["item"], "total": detector.stats()["total_observations"]})

    @app.get("/api/v1/novelty/is_novel")
    async def api_novelty_is_novel(item: str = Query(...)) -> JSONResponse:
        try:
            is_novel = detector.is_novel(item)
        except NoveltyDetectorError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"item": item, "is_novel": is_novel})

    @app.get("/api/v1/novelty/rate")
    async def api_novelty_rate() -> JSONResponse:
        return JSONResponse({"novelty_rate": detector.novelty_rate()})

    @app.get("/api/v1/novelty/surprise")
    async def api_novelty_surprise(item: str = Query(...)) -> JSONResponse:
        try:
            score = detector.surprise_score(item)
        except NoveltyDetectorError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"item": item, "surprise_score": score})

    @app.get("/api/v1/novelty/stats")
    async def api_novelty_stats() -> JSONResponse:
        return JSONResponse(detector.stats())

    @app.delete("/api/v1/novelty/reset")
    async def api_novelty_reset() -> JSONResponse:
        detector.reset()
        return JSONResponse(detector.stats())

    return detector
