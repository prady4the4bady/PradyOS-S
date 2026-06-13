"""HTTP surface for EVOLVE — the autonomous self-improvement pipeline.

Registers ``/api/v1/evolve/*``: evaluate a proposed self-modification (compose
FORTIFY robustness + REVIEW GATE safety into one verdict) and inspect prior
evaluations. Factory-scoped, fully local/deterministic (judges source, never
runs it).
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.evolve import EvolveEngine, EvolveError
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_evolve_routes(app: Any, evolve: Any | None = None) -> Any:
    """Register the ``/api/v1/evolve`` routes on ``app``; return the engine used."""
    eng: EvolveEngine = evolve if evolve is not None else EvolveEngine()

    @app.post("/api/v1/evolve/evaluate")
    async def api_evolve_evaluate(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "path" not in body or "after" not in body:
            return JSONResponse({"error": "path and after are required"}, status_code=422)
        if not isinstance(body["after"], str):
            return JSONResponse({"error": "after must be a string"}, status_code=422)
        before = body.get("before", "")
        if not isinstance(before, str):
            return JSONResponse({"error": "before must be a string"}, status_code=422)
        try:
            return JSONResponse(eng.evaluate(body["path"], body["after"], before))
        except EvolveError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/evolve/evaluation")
    async def api_evolve_evaluation(seq: int = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(eng.evaluation(seq))
        except EvolveError as exc:
            return _err(exc)

    @app.get("/api/v1/evolve/evaluations")
    async def api_evolve_evaluations(limit: int = Query(20)) -> JSONResponse:
        try:
            return JSONResponse({"evaluations": eng.evaluations(limit=limit)})
        except EvolveError as exc:
            return _err(exc)

    @app.get("/api/v1/evolve/stats")
    async def api_evolve_stats() -> JSONResponse:
        return JSONResponse(eng.stats())

    @app.delete("/api/v1/evolve/reset")
    async def api_evolve_reset() -> JSONResponse:
        eng.reset()
        return JSONResponse(eng.stats())

    return eng
