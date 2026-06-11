"""HTTP surface for HELIOS FORGE — the build engine (Plane / Agent 2).

Registers ``/api/v1/helios/*``: create a build for an approved project, advance
it through the gated stages, track milestones / artifacts / test results, and
read manifests. The forge instance is factory-scoped (one per app).
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.helios_forge import ForgeError, HeliosForge


def _err(exc: ForgeError) -> JSONResponse:
    code = 404 if "unknown" in str(exc) else 422
    return JSONResponse({"error": str(exc)}, status_code=code)


async def _json(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        return None


def register_helios_routes(app: Any, helios: Any | None = None) -> Any:
    """Register the ``/api/v1/helios`` routes on ``app``; return the forge used."""
    forge: HeliosForge = helios if helios is not None else HeliosForge()

    @app.post("/api/v1/helios/build")
    async def api_helios_create(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body or "project" not in body:
            return JSONResponse({"error": "id and project are required"}, status_code=422)
        try:
            return JSONResponse(forge.create(body["id"], body["project"]))
        except ForgeError as exc:
            return _err(exc)

    @app.post("/api/v1/helios/advance")
    async def api_helios_advance(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "build_id" not in body:
            return JSONResponse({"error": "build_id is required"}, status_code=422)
        try:
            return JSONResponse(forge.advance(body["build_id"]))
        except ForgeError as exc:
            return _err(exc)

    @app.post("/api/v1/helios/milestone")
    async def api_helios_milestone(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "build_id" not in body or "name" not in body:
            return JSONResponse({"error": "build_id and name are required"}, status_code=422)
        complete = body.get("complete", False)
        if not isinstance(complete, bool):
            return JSONResponse({"error": "complete must be a boolean"}, status_code=422)
        try:
            if complete:
                return JSONResponse(forge.complete_milestone(body["build_id"], body["name"]))
            return JSONResponse(forge.add_milestone(body["build_id"], body["name"]))
        except ForgeError as exc:
            return _err(exc)

    @app.post("/api/v1/helios/artifact")
    async def api_helios_artifact(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or not all(k in body for k in ("build_id", "name", "kind")):
            return JSONResponse({"error": "build_id, name, kind are required"}, status_code=422)
        try:
            return JSONResponse(forge.record_artifact(body["build_id"], body["name"], body["kind"]))
        except ForgeError as exc:
            return _err(exc)

    @app.post("/api/v1/helios/tests")
    async def api_helios_tests(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or not all(
            k in body for k in ("build_id", "passed", "failed")
        ):
            return JSONResponse({"error": "build_id, passed, failed are required"}, status_code=422)
        try:
            return JSONResponse(
                forge.record_tests(body["build_id"], body["passed"], body["failed"])
            )
        except ForgeError as exc:
            return _err(exc)

    @app.get("/api/v1/helios/build")
    async def api_helios_manifest(build_id: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(forge.manifest(build_id))
        except ForgeError as exc:
            return _err(exc)

    @app.get("/api/v1/helios/builds")
    async def api_helios_builds() -> JSONResponse:
        return JSONResponse({"builds": forge.builds()})

    @app.get("/api/v1/helios/stats")
    async def api_helios_stats() -> JSONResponse:
        return JSONResponse(forge.stats())

    @app.delete("/api/v1/helios/reset")
    async def api_helios_reset() -> JSONResponse:
        forge.reset()
        return JSONResponse(forge.stats())

    return forge
