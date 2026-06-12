"""HTTP surface for BASTION — the security shield (Plane 7).

Registers ``/api/v1/bastion/*``: assess an action, scan untrusted content for
prompt-injection, map a risk score to a response tier, and read stats/history.
The shield instance is factory-scoped (one per app), never a global.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.bastion import Action, Bastion, BastionError

_BOOL_FIELDS = ("reversible", "privileged", "egress", "destructive")


def register_bastion_routes(app: Any, bastion: Any | None = None) -> Any:
    """Register the ``/api/v1/bastion`` routes on ``app``; return the shield used."""
    shield: Bastion = bastion if bastion is not None else Bastion()

    @app.post("/api/v1/bastion/assess")
    async def api_bastion_assess(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=422)
        if not isinstance(body, dict) or "kind" not in body:
            return JSONResponse({"error": "kind is required"}, status_code=422)
        for fld in _BOOL_FIELDS:
            if fld in body and not isinstance(body[fld], bool):
                return JSONResponse({"error": f"{fld} must be a boolean"}, status_code=422)
        try:
            action = Action(
                kind=body["kind"],
                target=body.get("target", ""),
                reversible=body.get("reversible", True),
                privileged=body.get("privileged", False),
                egress=body.get("egress", False),
                destructive=body.get("destructive", False),
                data_class=body.get("data_class", "internal"),
            )
            verdict = shield.assess(action)
        except BastionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(verdict.to_dict())

    @app.post("/api/v1/bastion/scan")
    async def api_bastion_scan(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=422)
        if not isinstance(body, dict) or "text" not in body or not isinstance(body["text"], str):
            return JSONResponse({"error": "text (string) is required"}, status_code=422)
        return JSONResponse(shield.scan_content(body["text"]))

    @app.get("/api/v1/bastion/response")
    async def api_bastion_response(risk_score: int = Query(...)) -> JSONResponse:
        try:
            tier = Bastion.response_for(risk_score)
        except BastionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"risk_score": risk_score, "response": tier})

    @app.get("/api/v1/bastion/stats")
    async def api_bastion_stats() -> JSONResponse:
        return JSONResponse(shield.stats())

    @app.get("/api/v1/bastion/history")
    async def api_bastion_history(limit: int = Query(50)) -> JSONResponse:
        return JSONResponse({"history": shield.history(limit=limit)})

    @app.delete("/api/v1/bastion/reset")
    async def api_bastion_reset() -> JSONResponse:
        shield.reset()
        return JSONResponse(shield.stats())

    return shield
