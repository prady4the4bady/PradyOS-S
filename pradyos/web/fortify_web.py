"""HTTP surface for FORTIFY — the agent's self-hardening audit.

Registers ``/api/v1/fortify/*``: audit Python source for robustness weaknesses,
read the resulting hardening reports, and list the rule catalogue. Factory-scoped,
fully local/deterministic (scans source, never runs it).
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.fortify import FortifyEngine, FortifyError
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_fortify_routes(app: Any, fortify: Any | None = None) -> Any:
    """Register the ``/api/v1/fortify`` routes on ``app``; return the engine used."""
    eng: FortifyEngine = fortify if fortify is not None else FortifyEngine()

    @app.post("/api/v1/fortify/audit")
    async def api_fortify_audit(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "module" not in body or "source" not in body:
            return JSONResponse({"error": "module and source are required"}, status_code=422)
        if not isinstance(body["source"], str):
            return JSONResponse({"error": "source must be a string"}, status_code=422)
        try:
            return JSONResponse(eng.audit(body["module"], body["source"]))
        except FortifyError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/fortify/report")
    async def api_fortify_report(module: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(eng.report(module))
        except FortifyError as exc:
            return _err(exc)

    @app.get("/api/v1/fortify/reports")
    async def api_fortify_reports() -> JSONResponse:
        return JSONResponse({"reports": eng.reports()})

    @app.get("/api/v1/fortify/rules")
    async def api_fortify_rules() -> JSONResponse:
        return JSONResponse({"rules": eng.rules()})

    @app.get("/api/v1/fortify/stats")
    async def api_fortify_stats() -> JSONResponse:
        return JSONResponse(eng.stats())

    @app.delete("/api/v1/fortify/reset")
    async def api_fortify_reset() -> JSONResponse:
        eng.reset()
        return JSONResponse(eng.stats())

    return eng
