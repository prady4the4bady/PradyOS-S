"""HTTP surface for DRIVE — the goal/drive manager (autonomy L3).

Registers ``/api/v1/drive/*``: propose a goal, list/inspect goals, approve or
reject (the Sovereign gate), and RUN an approved goal through the Guild. A goal
can only be run once approved — the OS never acts on an unapproved goal.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from pradyos.drive import DriveError, DriveManager
from pradyos.web._responses import read_json as _json


def register_drive_routes(
    app: Any,
    drive: Any | None = None,
    guild_runner: Any | None = None,
    critic: Any | None = None,
) -> Any:
    """Register ``/api/v1/drive`` routes; return the manager. ``guild_runner`` is an
    optional callable(objective:str)->dict used to execute an approved goal.
    ``critic`` is an optional CriticEnsemble that vetoes a run on a safety blocker —
    so even a Sovereign-approved goal can't execute if it's dangerous (L4 gate)."""
    mgr: DriveManager = drive if drive is not None else DriveManager()

    @app.post("/api/v1/drive/propose")
    async def api_drive_propose(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or not body.get("text"):
            return JSONResponse({"error": "text is required"}, status_code=422)
        try:
            return JSONResponse(mgr.propose(str(body["text"]), str(body.get("source", "user"))))
        except DriveError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/drive/goals")
    async def api_drive_goals(status: str | None = Query(None)) -> JSONResponse:
        try:
            return JSONResponse({"goals": mgr.list(status)})
        except DriveError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/drive/stats")
    async def api_drive_stats() -> JSONResponse:
        return JSONResponse(mgr.stats())

    @app.post("/api/v1/drive/{goal_id}/approve")
    async def api_drive_approve(goal_id: str) -> JSONResponse:
        try:
            return JSONResponse(mgr.approve(goal_id))
        except DriveError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @app.post("/api/v1/drive/{goal_id}/reject")
    async def api_drive_reject(goal_id: str) -> JSONResponse:
        try:
            return JSONResponse(mgr.reject(goal_id))
        except DriveError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @app.post("/api/v1/drive/{goal_id}/run")
    async def api_drive_run(goal_id: str) -> JSONResponse:
        """Execute an APPROVED goal through the Guild, then mark it done."""
        try:
            goal = mgr.get(goal_id)
        except DriveError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        if goal["status"] != "approved":
            return JSONResponse(
                {"error": f"goal is {goal['status']!r}; approve it before running"},
                status_code=409,
            )
        if guild_runner is None:
            return JSONResponse({"error": "no guild runner wired"}, status_code=503)
        # L4 gate: the critic ensemble vetoes a dangerous goal even if approved.
        if critic is not None:
            verdict = critic.judge(goal["text"])
            if verdict["verdict"] == "reject":
                return JSONResponse(
                    {"error": "critic ensemble vetoed this goal", "verdict": verdict},
                    status_code=403,
                )
        mgr.activate(goal_id)
        try:
            result = await run_in_threadpool(guild_runner, goal["text"])
        except Exception as exc:  # noqa: BLE001 — surface the failure, leave goal active
            return JSONResponse({"error": f"run failed: {exc}"}, status_code=502)
        summary = ""
        if isinstance(result, dict):
            summary = str(result.get("synthesis") or result.get("summary") or "")[:2000]
        return JSONResponse(mgr.complete(goal_id, summary))

    @app.delete("/api/v1/drive/reset")
    async def api_drive_reset() -> JSONResponse:
        mgr.reset()
        return JSONResponse(mgr.stats())

    return mgr
