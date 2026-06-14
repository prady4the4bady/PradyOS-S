"""HTTP surface for FORESIGHT — predict → act → compare → learn.

Registers ``/api/v1/foresight/*``: deliberate over candidate actions, observe a
realised outcome (the OS learns from it), recall past episodes for an action, and
read calibration stats. Factory-scoped, deterministic, fully offline.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.foresight import ForesightEngine, ForesightError
from pradyos.web._responses import read_json as _json


def register_foresight_routes(app: Any, engine: Any | None = None) -> Any:
    """Register the ``/api/v1/foresight`` routes on ``app``; return the engine."""
    eng: ForesightEngine = engine if engine is not None else ForesightEngine()

    @app.post("/api/v1/foresight/deliberate")
    async def api_foresight_deliberate(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict):
            return JSONResponse({"error": "object body required"}, status_code=422)
        state = str(body.get("state", ""))
        actions = body.get("actions")
        if not isinstance(actions, list) or not actions:
            return JSONResponse({"error": "actions must be a non-empty list"}, status_code=422)
        try:
            return JSONResponse(eng.deliberate(state, [str(a) for a in actions]))
        except ForesightError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.post("/api/v1/foresight/observe")
    async def api_foresight_observe(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "action" not in body or "value" not in body:
            return JSONResponse({"error": "action and value are required"}, status_code=422)
        try:
            value = float(body["value"])
        except (TypeError, ValueError):
            return JSONResponse({"error": "value must be a number"}, status_code=422)
        ep = eng.observe(
            str(body.get("state", "")),
            str(body["action"]),
            value,
            note=str(body.get("note", "")),
        )
        return JSONResponse(ep.to_dict())

    @app.get("/api/v1/foresight/recall")
    async def api_foresight_recall(action: str = Query(...), limit: int = Query(5)) -> JSONResponse:
        return JSONResponse({"episodes": [e.to_dict() for e in eng.recall(action, limit)]})

    @app.get("/api/v1/foresight/stats")
    async def api_foresight_stats() -> JSONResponse:
        return JSONResponse(eng.stats())

    @app.get("/api/v1/foresight/history")
    async def api_foresight_history(limit: int = Query(20)) -> JSONResponse:
        return JSONResponse({"history": eng.history(limit)})

    @app.delete("/api/v1/foresight/reset")
    async def api_foresight_reset() -> JSONResponse:
        eng.reset()
        return JSONResponse(eng.stats())

    return eng
