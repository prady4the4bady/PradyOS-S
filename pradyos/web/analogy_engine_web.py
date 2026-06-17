"""Sovereign Analogy Engine HTTP routes (cognitive layer).

Exposes a :class:`~pradyos.core.analogy_engine.AnalogyEngine` over REST.
Routes are registered onto the FastAPI ``app`` built by
``sovereign_web.create_app()`` via :func:`register_analogy_routes`,
called *inside* the factory.

Routes (mounted under ``/api/v1/analogy``):
  POST /api/v1/analogy/observe     body ``{"analogy_id": "...", "source_tokens": [...], "target_tokens": [...]}``
  POST /api/v1/analogy/analogize   body ``{"source_tokens": [...], "target_tokens": [...], "top_k": 10}``
  POST /api/v1/analogy/complete    body ``{"source_tokens": [...], "top_k": 10}``
  GET  /api/v1/analogy/stats       — engine statistics
  POST /api/v1/analogy/reset       clear all state
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.analogy_engine import AnalogyEngine, AnalogyEngineError


def register_analogy_routes(app: Any, engine: Any | None = None) -> Any:
    if engine is None:
        engine = AnalogyEngine()

    @app.post("/api/v1/analogy/observe")
    async def api_analogy_observe(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=422)
        aid = body.get("analogy_id")
        src = body.get("source_tokens")
        tgt = body.get("target_tokens")
        if not aid:
            return JSONResponse({"error": "analogy_id is required"}, status_code=422)
        if not isinstance(src, list):
            return JSONResponse({"error": "source_tokens must be a list"}, status_code=422)
        if not isinstance(tgt, list):
            return JSONResponse({"error": "target_tokens must be a list"}, status_code=422)
        try:
            engine.observe(str(aid), [str(s) for s in src], [str(t) for t in tgt])
        except AnalogyEngineError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"analogy_id": str(aid), "status": "stored"})

    @app.post("/api/v1/analogy/analogize")
    async def api_analogy_analogize(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=422)
        src = body.get("source_tokens", [])
        tgt = body.get("target_tokens", [])
        top_k = body.get("top_k", 10)
        if not isinstance(src, list):
            return JSONResponse({"error": "source_tokens must be a list"}, status_code=422)
        if not isinstance(tgt, list):
            return JSONResponse({"error": "target_tokens must be a list"}, status_code=422)
        try:
            results = engine.analogize(
                [str(s) for s in src], [str(t) for t in tgt], top_k=int(top_k)
            )
        except AnalogyEngineError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"analogies": results})

    @app.post("/api/v1/analogy/complete")
    async def api_analogy_complete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=422)
        src = body.get("source_tokens", [])
        top_k = body.get("top_k", 10)
        if not isinstance(src, list):
            return JSONResponse({"error": "source_tokens must be a list"}, status_code=422)
        try:
            results = engine.complete([str(s) for s in src], top_k=int(top_k))
        except AnalogyEngineError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"completions": results})

    @app.get("/api/v1/analogy/stats")
    async def api_analogy_stats() -> JSONResponse:
        return JSONResponse(engine.stats())

    @app.post("/api/v1/analogy/reset")
    async def api_analogy_reset() -> JSONResponse:
        engine.reset()
        return JSONResponse(engine.stats())

    return engine
