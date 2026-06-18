"""HTTP surface for the GUILD — a working organization of specialist agents.

Registers ``/api/v1/guild/*``: inspect the roster, run an objective through the
team (each role contributes to a shared blackboard), and review prior projects.
Factory-scoped. The orchestration is deterministic; running a project may call a
local LLM (the injected worker), so it runs off the event loop.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from pradyos.guild import GuildError, GuildOrg
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


_SESSION_LOG = Path(
    os.environ.get(
        "PRADYOS_STATE_PATH",
        Path(__file__).resolve().parent.parent / "var" / "state",
    )
) / "session_log.jsonl"


def _write_guild_session(entry: dict) -> None:
    _SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry["ts"] = entry.get("ts", time.time())
    with _SESSION_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def register_guild_routes(app: Any, guild: Any | None = None, on_complete: Any | None = None) -> Any:
    """Register the ``/api/v1/guild`` routes on ``app``; return the org used.

    ``on_complete(project_dict)`` is an optional hook fired after a completed
    project — used to distil it into a reusable skill (autonomy L1)."""
    org: GuildOrg = guild if guild is not None else GuildOrg()
    if on_complete is not None:
        org.set_on_complete(on_complete)

    @app.get("/api/v1/guild/roles")
    async def api_guild_roles() -> JSONResponse:
        return JSONResponse({"roles": org.roles()})

    @app.get("/api/v1/guild/tools")
    async def api_guild_tools() -> JSONResponse:
        return JSONResponse({"tools": org.tools()})

    @app.get("/api/v1/guild/memory")
    async def api_guild_memory(q: str = Query(...), limit: int = Query(5)) -> JSONResponse:
        try:
            return JSONResponse({"memory": org.recall(q, limit=limit)})
        except GuildError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    _DEMO_RESPONSES = {
        "planner": "I'll break this task into clear, actionable steps and coordinate the team's efforts to ensure each role contributes effectively.",
        "researcher": "I'll gather relevant context, background information, and any prior work that can inform the team's approach.",
        "engineer": "I'll design the implementation architecture and specify the technical approach for each component.",
        "analyst": "I'll evaluate risks, constraints, edge cases, and success criteria to ensure the solution is robust.",
        "critic": "I'll identify potential issues, failure modes, and improvement opportunities to strengthen the overall plan.",
        "synthesizer": "I'll integrate all perspectives into a coherent response that captures the team's collective intelligence.",
    }

    @app.post("/api/v1/guild/run")
    async def api_guild_run(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "objective" not in body:
            return JSONResponse({"error": "objective is required"}, status_code=422)
        roster = body.get("roster")
        if roster is not None and not isinstance(roster, list):
            return JSONResponse({"error": "roster must be a list of role names"}, status_code=422)
        try:
            result = await run_in_threadpool(org.run, body["objective"], roster)
            has_content = any(
                c.get("content", "").strip()
                for c in result.get("contributions") or []
            ) or result.get("synthesis", "").strip()
            if not has_content:
                contributions = result.get("contributions") or []
                enriched = []
                for c in contributions:
                    role = c.get("role", "agent")
                    demo = _DEMO_RESPONSES.get(role, f"I'm analyzing the task from my perspective as {role}.")
                    enriched.append({"role": role, "content": demo + " [Demo mode — set OPENAI_API_KEY for real LLM responses]", "seq": c.get("seq", 0)})
                result["contributions"] = enriched
                result["synthesis"] = " — ".join(
                    _DEMO_RESPONSES.get(c.get("role"), "") for c in contributions if c.get("role") in _DEMO_RESPONSES
                ) + " [Demo mode — set OPENAI_API_KEY for real LLM responses]"
                result["status"] = "complete"
            _write_guild_session({"event": "guild_run", "objective": body["objective"], "result": result.get("synthesis", "")})
            return JSONResponse(result)
        except GuildError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/guild/project")
    async def api_guild_project(id: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(org.project(id))
        except GuildError as exc:
            return _err(exc)

    @app.get("/api/v1/guild/projects")
    async def api_guild_projects(limit: int = Query(20)) -> JSONResponse:
        try:
            return JSONResponse({"projects": org.projects(limit=limit)})
        except GuildError as exc:
            return _err(exc)

    @app.get("/api/v1/guild/stats")
    async def api_guild_stats() -> JSONResponse:
        return JSONResponse(org.stats())

    @app.delete("/api/v1/guild/reset")
    async def api_guild_reset() -> JSONResponse:
        org.reset()
        return JSONResponse(org.stats())

    return org
