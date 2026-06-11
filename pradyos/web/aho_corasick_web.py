"""Phase 142 — Sovereign Aho-Corasick HTTP routes.

Exposes an :class:`~pradyos.core.aho_corasick.AhoCorasick` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_ahocorasick_routes`, called *inside* the factory — the automaton lives in
factory scope (passed in, or created fresh per app), so there is no module-level singleton. All
routes are static (no path parameters), so none can shadow another.

A non-string / empty pattern or non-string text is a request error → **HTTP 422**. The
automaton auto-builds on the first ``search`` after a pattern is added.

Routes (mounted under ``/api/v1/ahocorasick``):
  POST   /api/v1/ahocorasick/add       body ``{"pattern"}`` — ``{pattern, added, num_patterns}``
  POST   /api/v1/ahocorasick/add_many  body ``{"patterns": [...]}`` — ``{added, num_patterns}``
  POST   /api/v1/ahocorasick/search    body ``{"text"}`` — ``{text, matches, count}``
  GET    /api/v1/ahocorasick/stats      ``{num_patterns, num_nodes, built}``
  DELETE /api/v1/ahocorasick/reset      (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.aho_corasick import AhoCorasick, AhoCorasickError


def register_ahocorasick_routes(app: Any, aho_corasick: Any | None = None) -> Any:
    """Register the /api/v1/ahocorasick routes on ``app``; return the automaton used.

    ``aho_corasick`` defaults to a fresh (empty) :class:`AhoCorasick` owned by this app instance
    (factory scope — never a module-level global)."""
    if aho_corasick is None:
        aho_corasick = AhoCorasick()

    @app.post("/api/v1/ahocorasick/add")
    async def api_ac_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "pattern" not in body:
            return JSONResponse({"error": "pattern is required"}, status_code=422)
        try:
            added = aho_corasick.add(body["pattern"])
        except AhoCorasickError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(
            {"pattern": body["pattern"], "added": added, "num_patterns": aho_corasick.num_patterns}
        )

    @app.post("/api/v1/ahocorasick/add_many")
    async def api_ac_add_many(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("patterns"), list):
            return JSONResponse({"error": "patterns list is required"}, status_code=422)
        try:
            added = aho_corasick.add_many(body["patterns"])
        except AhoCorasickError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"added": added, "num_patterns": aho_corasick.num_patterns})

    @app.post("/api/v1/ahocorasick/search")
    async def api_ac_search(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("text"), str):
            return JSONResponse({"error": "text string is required"}, status_code=422)
        try:
            matches = aho_corasick.search(body["text"])
        except AhoCorasickError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(
            {"text": body["text"], "matches": [list(m) for m in matches], "count": len(matches)}
        )

    @app.get("/api/v1/ahocorasick/stats")
    async def api_ac_stats() -> JSONResponse:
        return JSONResponse(aho_corasick.stats())

    @app.delete("/api/v1/ahocorasick/reset")
    async def api_ac_reset() -> JSONResponse:
        aho_corasick.reset()
        return JSONResponse(aho_corasick.stats())

    return aho_corasick
