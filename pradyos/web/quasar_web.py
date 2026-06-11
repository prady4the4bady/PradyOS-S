"""HTTP surface for QUASAR GATE — the inference router (Plane 8).

Registers ``/api/v1/quasar/*`` on the Sovereign Web app: register backends, route
a task to the best backend, inspect the fallback chain, toggle health, and read
stats. The router instance is factory-scoped (one per app), never a module global.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.quasar_gate import NoRouteError, QuasarGate, QuasarGateError, RouteRequest


def register_quasar_routes(app: Any, quasar: Any | None = None) -> Any:
    """Register the ``/api/v1/quasar`` routes on ``app``; return the gate used."""
    gate: QuasarGate = quasar if quasar is not None else QuasarGate()

    @app.post("/api/v1/quasar/backend")
    async def api_quasar_register(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "JSON object body required"}, status_code=422)
        required = ("name", "location", "capabilities", "latency_ms")
        missing = [k for k in required if k not in body]
        if missing:
            return JSONResponse({"error": f"missing: {missing}"}, status_code=422)
        try:
            gate.register(
                name=body["name"],
                location=body["location"],
                capabilities=body["capabilities"],
                latency_ms=int(body["latency_ms"]),
                cost=float(body.get("cost", 0.0)),
                vram_mb=int(body.get("vram_mb", 0)),
                max_concurrent=int(body.get("max_concurrent", 1)),
            )
        except (QuasarGateError, TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(gate.describe(body["name"]))

    @app.get("/api/v1/quasar/backends")
    async def api_quasar_backends() -> JSONResponse:
        return JSONResponse({"backends": [gate.describe(b.name) for b in gate.backends()]})

    @app.post("/api/v1/quasar/route")
    async def api_quasar_route(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "task_class" not in body:
            return JSONResponse({"error": "task_class is required"}, status_code=422)
        try:
            req = RouteRequest(
                task_class=body["task_class"],
                max_latency_ms=body.get("max_latency_ms"),
                local_only=bool(body.get("local_only", False)),
                priority=body.get("priority", "interactive"),
            )
            chosen = gate.route(req)
        except NoRouteError as exc:
            return JSONResponse({"error": str(exc), "routed": False}, status_code=409)
        except QuasarGateError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"routed": True, "backend": gate.describe(chosen.name)})

    @app.get("/api/v1/quasar/candidates")
    async def api_quasar_candidates(
        task_class: str = Query(...),
        max_latency_ms: int | None = Query(None),
        local_only: bool = Query(False),
        priority: str = Query("interactive"),
    ) -> JSONResponse:
        try:
            req = RouteRequest(
                task_class=task_class,
                max_latency_ms=max_latency_ms,
                local_only=local_only,
                priority=priority,
            )
            chain = [b.name for b in gate.candidates(req)]
        except QuasarGateError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"task_class": task_class, "candidates": chain})

    @app.post("/api/v1/quasar/health")
    async def api_quasar_health(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "name" not in body or "healthy" not in body:
            return JSONResponse({"error": "name and healthy are required"}, status_code=422)
        try:
            if bool(body["healthy"]):
                gate.mark_healthy(body["name"])
            else:
                gate.mark_unhealthy(body["name"])
        except QuasarGateError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        return JSONResponse(gate.describe(body["name"]))

    @app.get("/api/v1/quasar/stats")
    async def api_quasar_stats() -> JSONResponse:
        return JSONResponse(gate.stats())

    @app.delete("/api/v1/quasar/reset")
    async def api_quasar_reset() -> JSONResponse:
        gate.reset()
        return JSONResponse(gate.stats())

    return gate
