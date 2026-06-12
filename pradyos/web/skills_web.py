"""HTTP surface for the SKILL LIBRARY — learn-from-experience self-improvement.

Registers ``/api/v1/skills/*``: learn a skill, match it to an intent, reinforce
it from real outcomes, revise its steps, prune failing skills, and inspect the
library. Factory-scoped, fully local/deterministic (no egress).
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.skills import SkillError, SkillLibrary
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_skills_routes(app: Any, skills: Any | None = None) -> Any:
    """Register the ``/api/v1/skills`` routes on ``app``; return the library used."""
    lib: SkillLibrary = skills if skills is not None else SkillLibrary()

    @app.post("/api/v1/skills/learn")
    async def api_skills_learn(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or not all(
            k in body for k in ("id", "name", "trigger", "steps")
        ):
            return JSONResponse({"error": "id, name, trigger, steps are required"}, status_code=422)
        try:
            return JSONResponse(
                lib.learn(
                    body["id"],
                    body["name"],
                    body["trigger"],
                    body["steps"],
                    preconditions=body.get("preconditions", []),
                    example=body.get("example"),
                )
            )
        except SkillError as exc:
            return _err(exc)

    @app.post("/api/v1/skills/reinforce")
    async def api_skills_reinforce(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body or "success" not in body:
            return JSONResponse({"error": "id and success are required"}, status_code=422)
        if not isinstance(body["success"], bool):
            return JSONResponse({"error": "success must be a boolean"}, status_code=422)
        try:
            return JSONResponse(lib.reinforce(body["id"], body["success"], body.get("example")))
        except SkillError as exc:
            return _err(exc)

    @app.post("/api/v1/skills/revise")
    async def api_skills_revise(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body or "steps" not in body:
            return JSONResponse({"error": "id and steps are required"}, status_code=422)
        try:
            return JSONResponse(lib.revise(body["id"], body["steps"]))
        except SkillError as exc:
            return _err(exc)

    @app.post("/api/v1/skills/match")
    async def api_skills_match(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "intent" not in body:
            return JSONResponse({"error": "intent is required"}, status_code=422)
        limit = body.get("limit", 5)
        try:
            return JSONResponse(
                {"intent": body["intent"], "skills": lib.match(body["intent"], limit)}
            )
        except SkillError as exc:
            return _err(exc)

    @app.post("/api/v1/skills/prune")
    async def api_skills_prune(request: Request) -> JSONResponse:
        body = await _json(request)
        body = body if isinstance(body, dict) else {}
        kwargs: dict[str, Any] = {}
        if "min_confidence" in body:
            kwargs["min_confidence"] = body["min_confidence"]
        if "min_attempts" in body:
            kwargs["min_attempts"] = body["min_attempts"]
        try:
            return JSONResponse({"pruned": lib.prune(**kwargs)})
        except SkillError as exc:
            return _err(exc)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/skills/recall")
    async def api_skills_recall(id: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(lib.recall(id))
        except SkillError as exc:
            return _err(exc)

    @app.get("/api/v1/skills/list")
    async def api_skills_list() -> JSONResponse:
        return JSONResponse({"skills": lib.skills()})

    @app.get("/api/v1/skills/stats")
    async def api_skills_stats() -> JSONResponse:
        return JSONResponse(lib.stats())

    @app.delete("/api/v1/skills/reset")
    async def api_skills_reset() -> JSONResponse:
        lib.reset()
        return JSONResponse(lib.stats())

    return lib
