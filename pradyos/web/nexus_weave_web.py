"""HTTP surface for NEXUS WEAVE — agent orchestration / A2A routing (Agent 4).

Registers ``/api/v1/nexus/*``: register agents, submit tasks, route them
(internal-first, external A2A fallback), complete/fail, and inspect the queue.
Factory-scoped instance.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.nexus_weave import NexusError, NexusWeave, NoRouteError


def _err(exc: NexusError) -> JSONResponse:
    code = 404 if "unknown" in str(exc) else 422
    return JSONResponse({"error": str(exc)}, status_code=code)


async def _json(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        return None


def register_nexus_routes(app: Any, nexus: Any | None = None) -> Any:
    """Register the ``/api/v1/nexus`` routes on ``app``; return the router used."""
    weave: NexusWeave = nexus if nexus is not None else NexusWeave()

    @app.post("/api/v1/nexus/agent")
    async def api_nexus_agent(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or not all(
            k in body for k in ("name", "location", "capabilities")
        ):
            return JSONResponse(
                {"error": "name, location, capabilities are required"}, status_code=422
            )
        try:
            return JSONResponse(
                weave.register_agent(body["name"], body["location"], body["capabilities"])
            )
        except NexusError as exc:
            return _err(exc)

    @app.post("/api/v1/nexus/submit")
    async def api_nexus_submit(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "task_id" not in body or "kind" not in body:
            return JSONResponse({"error": "task_id and kind are required"}, status_code=422)
        try:
            return JSONResponse(weave.submit(body["task_id"], body["kind"]))
        except NexusError as exc:
            return _err(exc)

    @app.post("/api/v1/nexus/route")
    async def api_nexus_route(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "task_id" not in body:
            return JSONResponse({"error": "task_id is required"}, status_code=422)
        try:
            return JSONResponse(weave.route(body["task_id"]))
        except NoRouteError as exc:
            return JSONResponse({"error": str(exc), "routed": False}, status_code=409)
        except NexusError as exc:
            return _err(exc)

    @app.post("/api/v1/nexus/complete")
    async def api_nexus_complete(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "task_id" not in body:
            return JSONResponse({"error": "task_id is required"}, status_code=422)
        try:
            return JSONResponse(weave.complete(body["task_id"]))
        except NexusError as exc:
            return _err(exc)

    @app.post("/api/v1/nexus/fail")
    async def api_nexus_fail(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "task_id" not in body:
            return JSONResponse({"error": "task_id is required"}, status_code=422)
        try:
            return JSONResponse(weave.fail(body["task_id"], body.get("reason", "")))
        except NexusError as exc:
            return _err(exc)

    @app.get("/api/v1/nexus/agents")
    async def api_nexus_agents() -> JSONResponse:
        return JSONResponse({"agents": weave.agents()})

    @app.get("/api/v1/nexus/task")
    async def api_nexus_task(task_id: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(weave.task(task_id))
        except NexusError as exc:
            return _err(exc)

    @app.get("/api/v1/nexus/tasks")
    async def api_nexus_tasks() -> JSONResponse:
        return JSONResponse({"tasks": weave.tasks()})

    @app.get("/api/v1/nexus/stats")
    async def api_nexus_stats() -> JSONResponse:
        return JSONResponse(weave.stats())

    @app.delete("/api/v1/nexus/reset")
    async def api_nexus_reset() -> JSONResponse:
        weave.reset()
        return JSONResponse(weave.stats())

    return weave
