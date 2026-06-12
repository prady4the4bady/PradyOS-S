"""HTTP surface for NIGHT CITADEL — the self-improvement engine (Plane 9).

Registers ``/api/v1/citadel/*``: start a cycle, record the audit + candidates,
feed the gate inputs (gdi / constraints / regression), advance through the
gated phases, and read manifests. Factory-scoped instance, never a global.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.night_citadel import CitadelError, NightCitadel
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_citadel_routes(app: Any, citadel: Any | None = None) -> Any:
    """Register the ``/api/v1/citadel`` routes on ``app``; return the engine used."""
    engine: NightCitadel = citadel if citadel is not None else NightCitadel()

    @app.post("/api/v1/citadel/cycle")
    async def api_citadel_start(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body:
            return JSONResponse({"error": "id is required"}, status_code=422)
        try:
            return JSONResponse(engine.start_cycle(body["id"]))
        except CitadelError as exc:
            return _err(exc)

    @app.post("/api/v1/citadel/audit")
    async def api_citadel_audit(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "cycle_id" not in body or "failures" not in body:
            return JSONResponse({"error": "cycle_id and failures are required"}, status_code=422)
        try:
            return JSONResponse(engine.record_audit(body["cycle_id"], body["failures"]))
        except CitadelError as exc:
            return _err(exc)

    @app.post("/api/v1/citadel/candidate")
    async def api_citadel_candidate(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "cycle_id" not in body or "name" not in body:
            return JSONResponse({"error": "cycle_id and name are required"}, status_code=422)
        try:
            return JSONResponse(
                engine.add_candidate(body["cycle_id"], body["name"], body.get("target", ""))
            )
        except CitadelError as exc:
            return _err(exc)

    @app.post("/api/v1/citadel/gate")
    async def api_citadel_gate(request: Request) -> JSONResponse:
        """Set any of the gate inputs: gdi, constraints_ok, regression."""
        body = await _json(request)
        if not isinstance(body, dict) or "cycle_id" not in body:
            return JSONResponse({"error": "cycle_id is required"}, status_code=422)
        cid = body["cycle_id"]
        if "constraints_ok" in body and not isinstance(body["constraints_ok"], bool):
            return JSONResponse({"error": "constraints_ok must be a boolean"}, status_code=422)
        try:
            manifest = engine.manifest(cid)  # raises if unknown
            if "gdi" in body:
                manifest = engine.set_gdi(cid, body["gdi"])
            if "constraints_ok" in body:
                manifest = engine.set_constraints_ok(cid, body["constraints_ok"])
            if "regression" in body:
                manifest = engine.set_regression(cid, body["regression"])
            return JSONResponse(manifest)
        except CitadelError as exc:
            return _err(exc)

    @app.post("/api/v1/citadel/advance")
    async def api_citadel_advance(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "cycle_id" not in body:
            return JSONResponse({"error": "cycle_id is required"}, status_code=422)
        try:
            return JSONResponse(engine.advance(body["cycle_id"]))
        except CitadelError as exc:
            return _err(exc)

    @app.post("/api/v1/citadel/halt")
    async def api_citadel_halt(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "cycle_id" not in body:
            return JSONResponse({"error": "cycle_id is required"}, status_code=422)
        try:
            return JSONResponse(engine.halt(body["cycle_id"], body.get("reason", "manual halt")))
        except CitadelError as exc:
            return _err(exc)

    @app.get("/api/v1/citadel/cycle")
    async def api_citadel_manifest(cycle_id: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(engine.manifest(cycle_id))
        except CitadelError as exc:
            return _err(exc)

    @app.get("/api/v1/citadel/cycles")
    async def api_citadel_cycles() -> JSONResponse:
        return JSONResponse({"cycles": engine.cycles()})

    @app.get("/api/v1/citadel/stats")
    async def api_citadel_stats() -> JSONResponse:
        return JSONResponse(engine.stats())

    @app.delete("/api/v1/citadel/reset")
    async def api_citadel_reset() -> JSONResponse:
        engine.reset()
        return JSONResponse(engine.stats())

    return engine
