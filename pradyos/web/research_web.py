"""HTTP surface for RESEARCH — autonomous intelligence gathering.

Registers ``/api/v1/research/*``: run a research question across the registered
sources, inspect the resulting cited briefs, expand a question into sub-queries,
and list configured sources. Factory-scoped engine.

The default factory engine has **no live sources** registered (reading the open
web is a Sovereign-boundary egress decision); ``run`` then returns an empty,
well-formed brief noting that. Production wires a source — e.g.::

    from pradyos.research import ResearchEngine, WebAgentSource
    register_research_routes(app, ResearchEngine(sources=[WebAgentSource()]))
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.research import ResearchEngine, ResearchError
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def _opt_str_list(value: Any) -> list[str] | None:
    """Validate an optional list-of-strings body field; raise ValueError if bad."""
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError("must be a list of strings")
    return value


def register_research_routes(app: Any, engine: Any | None = None) -> Any:
    """Register the ``/api/v1/research`` routes on ``app``; return the engine used."""
    eng: ResearchEngine = engine if engine is not None else ResearchEngine()

    @app.post("/api/v1/research/run")
    async def api_research_run(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "question" not in body:
            return JSONResponse({"error": "question is required"}, status_code=422)
        try:
            providers = _opt_str_list(body.get("providers"))
            angles = _opt_str_list(body.get("angles"))
        except ValueError as exc:
            return JSONResponse({"error": f"providers/angles {exc}"}, status_code=422)
        kwargs: dict[str, Any] = {}
        if providers is not None:
            kwargs["providers"] = providers
        if angles is not None:
            kwargs["angles"] = tuple(angles)
        if "max_results" in body:
            kwargs["max_results_per_query"] = body["max_results"]
        if "max_findings" in body:
            kwargs["max_findings"] = body["max_findings"]
        try:
            brief = eng.research(body["question"], **kwargs)
        except ResearchError as exc:
            return _err(exc)
        except (TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(brief.to_dict())

    @app.post("/api/v1/research/plan")
    async def api_research_plan(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "question" not in body:
            return JSONResponse({"error": "question is required"}, status_code=422)
        try:
            angles = _opt_str_list(body.get("angles"))
        except ValueError as exc:
            return JSONResponse({"error": f"angles {exc}"}, status_code=422)
        try:
            queries = eng.plan_queries(
                body["question"], angles=tuple(angles) if angles is not None else None
            )
        except ResearchError as exc:
            return _err(exc)
        return JSONResponse({"question": body["question"], "queries": queries})

    @app.get("/api/v1/research/brief")
    async def api_research_brief(seq: int = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(eng.brief(seq))
        except ResearchError as exc:
            return _err(exc)

    @app.get("/api/v1/research/briefs")
    async def api_research_briefs(limit: int = Query(20)) -> JSONResponse:
        try:
            return JSONResponse({"briefs": eng.briefs(limit=limit)})
        except ResearchError as exc:
            return _err(exc)

    @app.get("/api/v1/research/sources")
    async def api_research_sources() -> JSONResponse:
        return JSONResponse({"sources": eng.sources()})

    @app.get("/api/v1/research/stats")
    async def api_research_stats() -> JSONResponse:
        return JSONResponse(eng.stats())

    @app.delete("/api/v1/research/reset")
    async def api_research_reset() -> JSONResponse:
        eng.reset()
        return JSONResponse(eng.stats())

    return eng
