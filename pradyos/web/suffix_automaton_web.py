"""Phase 151 — Sovereign Suffix Automaton HTTP routes.

Exposes a :class:`~pradyos.core.suffix_automaton.SuffixAutomaton` over REST. Routes are registered
onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_suffixautomaton_routes`, called *inside* the factory — the automaton lives in
factory scope (passed in, or created fresh per app), so there is no module-level singleton. All
routes are static (no path parameters), so none can shadow another.

A non-string ``text``/``pattern`` or a non-single-character ``extend`` is a request error →
**HTTP 422**.

Routes (mounted under ``/api/v1/suffixautomaton``):
  POST   /api/v1/suffixautomaton/build              body ``{"text"}`` — rebuild, returns stats
  POST   /api/v1/suffixautomaton/extend             body ``{"ch"}`` — ``{ch, num_states, length}``
  GET    /api/v1/suffixautomaton/contains           query ``?pattern=`` — ``{pattern, contains}``
  GET    /api/v1/suffixautomaton/distinct_substrings  ``{distinct_substrings}``
  GET    /api/v1/suffixautomaton/stats               ``{num_states, length, distinct_substrings, transitions}``
  DELETE /api/v1/suffixautomaton/reset               clear back to the empty string
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.suffix_automaton import SuffixAutomaton, SuffixAutomatonError


def register_suffixautomaton_routes(app: Any, suffix_automaton: Any | None = None) -> Any:
    """Register the /api/v1/suffixautomaton routes on ``app``; return the automaton used.

    ``suffix_automaton`` defaults to a fresh empty :class:`SuffixAutomaton` owned by this app
    instance (factory scope — never a module-level global)."""
    if suffix_automaton is None:
        suffix_automaton = SuffixAutomaton()
    sam = suffix_automaton

    @app.post("/api/v1/suffixautomaton/build")
    async def api_sam_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "text" not in body:
            return JSONResponse({"error": "text is required"}, status_code=422)
        try:
            sam.build(body["text"])
        except SuffixAutomatonError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(sam.stats())

    @app.post("/api/v1/suffixautomaton/extend")
    async def api_sam_extend(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "ch" not in body:
            return JSONResponse({"error": "ch is required"}, status_code=422)
        try:
            sam.extend(body["ch"])
        except SuffixAutomatonError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"ch": body["ch"], "num_states": sam.num_states, "length": sam.length})

    @app.get("/api/v1/suffixautomaton/contains")
    async def api_sam_contains(pattern: str = Query("")) -> JSONResponse:
        try:
            present = sam.contains(pattern)
        except SuffixAutomatonError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"pattern": pattern, "contains": present})

    @app.get("/api/v1/suffixautomaton/distinct_substrings")
    async def api_sam_distinct() -> JSONResponse:
        return JSONResponse({"distinct_substrings": sam.distinct_substrings()})

    @app.get("/api/v1/suffixautomaton/stats")
    async def api_sam_stats() -> JSONResponse:
        return JSONResponse(sam.stats())

    @app.delete("/api/v1/suffixautomaton/reset")
    async def api_sam_reset() -> JSONResponse:
        sam.reset()
        return JSONResponse(sam.stats())

    return sam
