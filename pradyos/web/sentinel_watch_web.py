"""HTTP surface for SENTINEL WATCH — adversarial defense (Agent 5).

Registers ``/api/v1/sentinel/*``: register red-team scenarios, record exercise
outcomes, patch breaches, and read the security posture. Factory-scoped instance.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.sentinel_watch import SentinelError, SentinelWatch
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_sentinel_routes(app: Any, sentinel: Any | None = None) -> Any:
    """Register the ``/api/v1/sentinel`` routes on ``app``; return the engine used."""
    watch: SentinelWatch = sentinel if sentinel is not None else SentinelWatch()

    @app.post("/api/v1/sentinel/scenario")
    async def api_sentinel_scenario(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "name" not in body or "boundary" not in body:
            return JSONResponse({"error": "name and boundary are required"}, status_code=422)
        try:
            return JSONResponse(watch.register_scenario(body["name"], body["boundary"]))
        except SentinelError as exc:
            return _err(exc)

    @app.post("/api/v1/sentinel/run")
    async def api_sentinel_run(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "name" not in body or "breached" not in body:
            return JSONResponse({"error": "name and breached are required"}, status_code=422)
        if not isinstance(body["breached"], bool):
            return JSONResponse({"error": "breached must be a boolean"}, status_code=422)
        try:
            return JSONResponse(watch.run(body["name"], body["breached"], body.get("note", "")))
        except SentinelError as exc:
            return _err(exc)

    @app.post("/api/v1/sentinel/patch")
    async def api_sentinel_patch(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "name" not in body:
            return JSONResponse({"error": "name is required"}, status_code=422)
        try:
            return JSONResponse(watch.patch(body["name"]))
        except SentinelError as exc:
            return _err(exc)

    @app.get("/api/v1/sentinel/posture")
    async def api_sentinel_posture() -> JSONResponse:
        return JSONResponse(watch.posture())

    @app.get("/api/v1/sentinel/scenarios")
    async def api_sentinel_scenarios() -> JSONResponse:
        return JSONResponse({"scenarios": watch.scenarios()})

    @app.get("/api/v1/sentinel/history")
    async def api_sentinel_history(limit: int = Query(50)) -> JSONResponse:
        return JSONResponse({"history": watch.history(limit=limit)})

    @app.delete("/api/v1/sentinel/reset")
    async def api_sentinel_reset() -> JSONResponse:
        watch.reset()
        return JSONResponse(watch.posture())

    return watch
