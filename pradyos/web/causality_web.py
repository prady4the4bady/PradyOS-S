"""HTTP surface for CAUSALITY — counterfactual credit assignment (autonomy L5).

Registers ``/api/v1/causality/*``: record a trial, ask the counterfactual for a
cause→effect pair, rank the causes of an effect, and inspect stats. Offline,
deterministic.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.causality import CausalEngine, CausalError
from pradyos.web._responses import read_json as _json


def register_causality_routes(app: Any, engine: Any | None = None) -> Any:
    """Register the ``/api/v1/causality`` routes on ``app``; return the engine."""
    eng: CausalEngine = engine if engine is not None else CausalEngine()

    @app.post("/api/v1/causality/observe")
    async def api_causality_observe(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict):
            return JSONResponse({"error": "object body required"}, status_code=422)
        causes = body.get("causes") or []
        effects = body.get("effects") or []
        if not isinstance(causes, list) or not isinstance(effects, list):
            return JSONResponse({"error": "causes and effects must be lists"}, status_code=422)
        try:
            return JSONResponse(eng.observe(causes, effects))
        except CausalError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/causality/counterfactual")
    async def api_causality_counterfactual(
        cause: str = Query(...), effect: str = Query(...)
    ) -> JSONResponse:
        return JSONResponse(eng.counterfactual(cause, effect))

    @app.get("/api/v1/causality/attribute")
    async def api_causality_attribute(effect: str = Query(...), limit: int = Query(5)) -> JSONResponse:
        return JSONResponse({"effect": effect, "causes": eng.attribute(effect, limit)})

    @app.get("/api/v1/causality/stats")
    async def api_causality_stats() -> JSONResponse:
        return JSONResponse(eng.stats())

    @app.delete("/api/v1/causality/reset")
    async def api_causality_reset() -> JSONResponse:
        eng.reset()
        return JSONResponse(eng.stats())

    return eng
