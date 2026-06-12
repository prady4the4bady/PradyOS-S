"""HTTP surface for AETHER SHELL — the experience layer (Plane 10).

Registers ``/api/v1/aether/*``: capture Sovereign intent, push/ack governance
cards, and read the composed governance-chamber experience. Factory-scoped.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.aether_shell import AetherError, AetherShell


def _err(exc: AetherError) -> JSONResponse:
    code = 404 if "unknown" in str(exc) else 422
    return JSONResponse({"error": str(exc)}, status_code=code)


async def _json(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        return None


def register_aether_routes(app: Any, aether: Any | None = None) -> Any:
    """Register the ``/api/v1/aether`` routes on ``app``; return the shell used."""
    shell: AetherShell = aether if aether is not None else AetherShell()

    @app.post("/api/v1/aether/intent")
    async def api_aether_intent(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body or "text" not in body:
            return JSONResponse({"error": "id and text are required"}, status_code=422)
        try:
            return JSONResponse(shell.capture_intent(body["id"], body["text"]))
        except AetherError as exc:
            return _err(exc)

    @app.post("/api/v1/aether/card")
    async def api_aether_card(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or not all(k in body for k in ("id", "surface", "title")):
            return JSONResponse({"error": "id, surface, title are required"}, status_code=422)
        try:
            return JSONResponse(
                shell.push_card(
                    body["id"],
                    body["surface"],
                    body["title"],
                    urgency=body.get("urgency", "info"),
                    body=body.get("body", ""),
                )
            )
        except AetherError as exc:
            return _err(exc)

    @app.post("/api/v1/aether/ack")
    async def api_aether_ack(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body:
            return JSONResponse({"error": "id is required"}, status_code=422)
        try:
            return JSONResponse(shell.ack_card(body["id"]))
        except AetherError as exc:
            return _err(exc)

    @app.get("/api/v1/aether/experience")
    async def api_aether_experience() -> JSONResponse:
        return JSONResponse(shell.experience())

    @app.get("/api/v1/aether/intents")
    async def api_aether_intents(limit: int = Query(50)) -> JSONResponse:
        return JSONResponse({"intents": shell.intents(limit=limit)})

    @app.get("/api/v1/aether/stats")
    async def api_aether_stats() -> JSONResponse:
        return JSONResponse(shell.stats())

    @app.delete("/api/v1/aether/reset")
    async def api_aether_reset() -> JSONResponse:
        shell.reset()
        return JSONResponse(shell.stats())

    return shell
