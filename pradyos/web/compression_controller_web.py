"""Sovereign Compression Controller HTTP routes (cognitive layer).

Exposes a :class:`~pradyos.core.compression_controller.CompressionController`
over REST.  Routes are registered onto the FastAPI ``app`` built by
``sovereign_web.create_app()`` via :func:`register_compression_routes`.

Routes (mounted under ``/api/v1/compression``):
  GET  /api/v1/compression/strategies         — list available strategies
  POST /api/v1/compression/feed               — feed items through a strategy
  POST /api/v1/compression/summarize          — get compressed summary
  POST /api/v1/compression/estimate           — estimate compression ratio
  GET  /api/v1/compression/stats              — controller statistics
  POST /api/v1/compression/reset              — clear state
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.compression_controller import (
    CompressionController,
    CompressionControllerError,
)


def register_compression_routes(app: Any, controller: Any | None = None) -> Any:
    if controller is None:
        controller = CompressionController()

    @app.get("/api/v1/compression/strategies")
    async def api_compression_strategies() -> JSONResponse:
        return JSONResponse({"strategies": controller.strategies()})

    @app.post("/api/v1/compression/feed")
    async def api_compression_feed(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=422)
        if not isinstance(body.get("items"), list):
            return JSONResponse({"error": "items must be a list"}, status_code=422)
        items = body["items"]
        strategy = str(body.get("strategy", "topk"))
        try:
            result = controller.feed([str(i) for i in items], strategy)
        except CompressionControllerError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(result)

    @app.post("/api/v1/compression/summarize")
    async def api_compression_summarize(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=422)
        strategy = str(body.get("strategy", "topk"))
        try:
            result = controller.summarize(strategy)
        except CompressionControllerError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(result)

    @app.post("/api/v1/compression/estimate")
    async def api_compression_estimate(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=422)
        if not isinstance(body.get("items"), list):
            return JSONResponse({"error": "items must be a list"}, status_code=422)
        items = body["items"]
        strategy = str(body.get("strategy", "topk"))
        try:
            result = controller.estimate_size(items, strategy)
        except CompressionControllerError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(result)

    @app.get("/api/v1/compression/stats")
    async def api_compression_stats() -> JSONResponse:
        return JSONResponse(controller.stats())

    @app.post("/api/v1/compression/reset")
    async def api_compression_reset(request: Request) -> JSONResponse:
        body = await request.json() if await request.body() else {}
        strategy = body.get("strategy") if isinstance(body, dict) else None
        controller.reset(strategy=strategy)
        return JSONResponse({"status": "reset", "strategy": strategy or "all"})

    return controller
