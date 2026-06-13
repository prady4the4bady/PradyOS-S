"""HTTP surface for ASCENT — the autonomous self-improvement loop.

Registers ``/api/v1/ascent/*``: survey the agent's own modules to choose a
hardening target, run a full self-improvement cycle (survey → direct → EVOLVE
propose+gate → decide), and inspect prior cycles and the apply queue.
Factory-scoped. The survey/decide core is deterministic; running a cycle may
call a local LLM (inside the injected EVOLVE engine), so it runs off the event
loop.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from pradyos.ascent import AscentError, AscentLoop
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_ascent_routes(app: Any, ascent: Any | None = None) -> Any:
    """Register the ``/api/v1/ascent`` routes on ``app``; return the loop used."""
    loop: AscentLoop = ascent if ascent is not None else AscentLoop()

    @app.post("/api/v1/ascent/survey")
    async def api_ascent_survey(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "candidates" not in body:
            return JSONResponse({"error": "candidates is required"}, status_code=422)
        try:
            return JSONResponse({"survey": loop.survey(body["candidates"])})
        except AscentError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.post("/api/v1/ascent/cycle")
    async def api_ascent_cycle(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "candidates" not in body:
            return JSONResponse({"error": "candidates is required"}, status_code=422)
        max_targets = body.get("max_targets", 1)
        try:
            # run_cycle may call a (blocking) local LLM via EVOLVE — keep it off
            # the event loop.
            cycles = await run_in_threadpool(loop.run_cycle, body["candidates"], max_targets)
            return JSONResponse({"cycles": cycles})
        except AscentError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/ascent/cycle")
    async def api_ascent_get(seq: int = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(loop.cycle(seq))
        except AscentError as exc:
            return _err(exc)

    @app.get("/api/v1/ascent/cycles")
    async def api_ascent_list(limit: int = Query(20)) -> JSONResponse:
        try:
            return JSONResponse({"cycles": loop.cycles(limit=limit)})
        except AscentError as exc:
            return _err(exc)

    @app.get("/api/v1/ascent/pending")
    async def api_ascent_pending(limit: int = Query(20)) -> JSONResponse:
        try:
            return JSONResponse({"pending": loop.pending(limit=limit)})
        except AscentError as exc:
            return _err(exc)

    @app.get("/api/v1/ascent/queue")
    async def api_ascent_queue(limit: int = Query(20)) -> JSONResponse:
        try:
            return JSONResponse({"queue": loop.review_queue(limit=limit)})
        except AscentError as exc:
            return _err(exc)

    @app.post("/api/v1/ascent/resolve")
    async def api_ascent_resolve(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "seq" not in body or "decision" not in body:
            return JSONResponse({"error": "seq and decision are required"}, status_code=422)
        try:
            return JSONResponse(
                loop.resolve(body["seq"], body["decision"], body.get("by", "sovereign"))
            )
        except AscentError as exc:
            return _err(exc)

    @app.get("/api/v1/ascent/decisions")
    async def api_ascent_decisions(limit: int = Query(20)) -> JSONResponse:
        try:
            return JSONResponse({"decisions": loop.decisions(limit=limit)})
        except AscentError as exc:
            return _err(exc)

    @app.post("/api/v1/ascent/apply")
    async def api_ascent_apply(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "seq" not in body:
            return JSONResponse({"error": "seq is required"}, status_code=422)
        try:
            # apply() re-gates + writes to disk (staging) — keep the I/O off the loop.
            return JSONResponse(await run_in_threadpool(loop.apply, body["seq"]))
        except AscentError as exc:
            return _err(exc)

    @app.get("/api/v1/ascent/applied")
    async def api_ascent_applied(limit: int = Query(20)) -> JSONResponse:
        try:
            return JSONResponse({"applied": loop.applied(limit=limit)})
        except AscentError as exc:
            return _err(exc)

    @app.get("/api/v1/ascent/stats")
    async def api_ascent_stats() -> JSONResponse:
        return JSONResponse(loop.stats())

    @app.delete("/api/v1/ascent/reset")
    async def api_ascent_reset() -> JSONResponse:
        loop.reset()
        return JSONResponse(loop.stats())

    return loop
