"""HTTP surface for SPECTER — web-action executor (Plane / Agent — SPECTER).

Registers ``/api/v1/specter/*``: plan a target (API-first), create/run
checkpointed browser flows, extract state, and retry/fail steps. Factory-scoped.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.specter import Specter, SpecterError


def _err(exc: SpecterError) -> JSONResponse:
    code = 404 if "unknown" in str(exc) else 422
    return JSONResponse({"error": str(exc)}, status_code=code)


async def _json(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        return None


def register_specter_routes(app: Any, specter: Any | None = None) -> Any:
    """Register the ``/api/v1/specter`` routes on ``app``; return the runner used."""
    runner: Specter = specter if specter is not None else Specter()

    @app.get("/api/v1/specter/plan")
    async def api_specter_plan(
        target: str = Query(...), has_api: bool = Query(...)
    ) -> JSONResponse:
        try:
            return JSONResponse(Specter.plan(target, has_api))
        except SpecterError as exc:
            return _err(exc)

    @app.post("/api/v1/specter/flow")
    async def api_specter_flow(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or not all(k in body for k in ("id", "target", "steps")):
            return JSONResponse({"error": "id, target, steps are required"}, status_code=422)
        try:
            return JSONResponse(runner.create_flow(body["id"], body["target"], body["steps"]))
        except SpecterError as exc:
            return _err(exc)

    @app.post("/api/v1/specter/step")
    async def api_specter_step(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "flow_id" not in body:
            return JSONResponse({"error": "flow_id is required"}, status_code=422)
        try:
            return JSONResponse(runner.step(body["flow_id"]))
        except SpecterError as exc:
            return _err(exc)

    @app.post("/api/v1/specter/extract")
    async def api_specter_extract(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or not all(k in body for k in ("flow_id", "key", "value")):
            return JSONResponse({"error": "flow_id, key, value are required"}, status_code=422)
        try:
            return JSONResponse(runner.extract(body["flow_id"], body["key"], body["value"]))
        except SpecterError as exc:
            return _err(exc)

    @app.post("/api/v1/specter/fail")
    async def api_specter_fail(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "flow_id" not in body:
            return JSONResponse({"error": "flow_id is required"}, status_code=422)
        try:
            return JSONResponse(runner.fail_step(body["flow_id"], body.get("reason", "")))
        except SpecterError as exc:
            return _err(exc)

    @app.get("/api/v1/specter/flow")
    async def api_specter_get_flow(flow_id: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(runner.flow(flow_id))
        except SpecterError as exc:
            return _err(exc)

    @app.get("/api/v1/specter/flows")
    async def api_specter_flows() -> JSONResponse:
        return JSONResponse({"flows": runner.flows()})

    @app.get("/api/v1/specter/stats")
    async def api_specter_stats() -> JSONResponse:
        return JSONResponse(runner.stats())

    @app.delete("/api/v1/specter/reset")
    async def api_specter_reset() -> JSONResponse:
        runner.reset()
        return JSONResponse(runner.stats())

    return runner
