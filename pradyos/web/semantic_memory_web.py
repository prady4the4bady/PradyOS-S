"""Sovereign Semantic Memory HTTP routes (cognitive layer).

Exposes a :class:`~pradyos.core.semantic_memory.SemanticMemory` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()``
via :func:`register_semantic_routes`, called *inside* the factory — the memory
lives in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters).

Routes (mounted under ``/api/v1/semantic``):
  POST   /api/v1/semantic/store    body ``{"key","content","tokens":[...]}``
  POST   /api/v1/semantic/recall   body ``{"tokens":[...],"top_k"?,"min_similarity"?}``
  POST   /api/v1/semantic/forget   body ``{"threshold": x}`` — prune low-frequency items
  GET    /api/v1/semantic/stats    ``{size, num_hashes, simhash_bits, top_concepts, ...}``
  DELETE /api/v1/semantic/reset    clear all stored items
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.semantic_memory import SemanticMemory, SemanticMemoryError


def register_semantic_routes(app: Any, memory: Any | None = None) -> Any:
    """Register the /api/v1/semantic routes on ``app``; return the memory used.

    ``memory`` defaults to a fresh :class:`SemanticMemory` owned by this app
    instance (factory scope — never a module-level global)."""
    if memory is None:
        memory = SemanticMemory()

    @app.post("/api/v1/semantic/store")
    async def api_sem_store(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body or "tokens" not in body:
            return JSONResponse({"error": "key and tokens are required"}, status_code=422)
        if not isinstance(body["tokens"], list):
            return JSONResponse({"error": "tokens must be a list"}, status_code=422)
        try:
            memory.store(str(body["key"]), str(body.get("content", "")), body["tokens"])
        except SemanticMemoryError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"key": body["key"], "size": memory.stats()["size"]})

    @app.post("/api/v1/semantic/recall")
    async def api_sem_recall(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("tokens"), list):
            return JSONResponse({"error": "tokens (list) is required"}, status_code=422)
        top_k = body.get("top_k", 10)
        min_sim = body.get("min_similarity", 0.0)
        if not isinstance(top_k, int) or top_k <= 0:
            return JSONResponse({"error": "top_k must be a positive integer"}, status_code=422)
        try:
            min_sim = float(min_sim)
        except (TypeError, ValueError):
            return JSONResponse({"error": "min_similarity must be a number"}, status_code=422)
        try:
            results = memory.recall(body["tokens"], top_k=top_k, min_similarity=min_sim)
        except SemanticMemoryError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"results": results, "count": len(results)})

    @app.post("/api/v1/semantic/forget")
    async def api_sem_forget(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "threshold" not in body:
            return JSONResponse({"error": "threshold is required"}, status_code=422)
        try:
            threshold = float(body["threshold"])
        except (TypeError, ValueError):
            return JSONResponse({"error": "threshold must be a number"}, status_code=422)
        pruned = memory.forget(threshold)
        return JSONResponse({"pruned": pruned, "size": memory.stats()["size"]})

    @app.get("/api/v1/semantic/stats")
    async def api_sem_stats() -> JSONResponse:
        return JSONResponse(memory.stats())

    @app.delete("/api/v1/semantic/reset")
    async def api_sem_reset() -> JSONResponse:
        memory.reset()
        return JSONResponse(memory.stats())

    return memory
