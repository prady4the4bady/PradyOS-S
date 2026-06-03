"""Phase 148 — Sovereign Li Chao Tree HTTP routes.

Exposes a :class:`~pradyos.core.li_chao_tree.LiChaoTree` over REST. Routes are registered onto the
FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_lichao_routes`, called
*inside* the factory — the tree lives in factory scope (passed in, or created fresh per app), so
there is no module-level singleton. All routes are static (no path parameters), so none can shadow
another.

A non-numeric line, a malformed batch, an ``x`` outside the domain, or a bad reconfigure is a
request error → **HTTP 422**. ``query`` returns ``{"value": null}`` when no lines have been added.

Routes (mounted under ``/api/v1/lichao``):
  POST   /api/v1/lichao/add_line   body ``{"m", "b"}`` — ``{m, b, num_lines}``
  POST   /api/v1/lichao/add_lines  body ``{"lines": [[m, b], ...]}`` — ``{added, num_lines}``
  GET    /api/v1/lichao/query      query ``?x=`` — ``{x, value}``  (value may be null)
  GET    /api/v1/lichao/stats       ``{num_lines, x_min, x_max, mode, nodes}``
  DELETE /api/v1/lichao/reset       body ``{"x_min"?, "x_max"?, "mode"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.li_chao_tree import LiChaoTree, LiChaoTreeError


def register_lichao_routes(app: Any, li_chao_tree: Any | None = None) -> Any:
    """Register the /api/v1/lichao routes on ``app``; return the tree used.

    ``li_chao_tree`` defaults to a fresh :class:`LiChaoTree` over ``[0, 1_000_000]`` in min-mode,
    owned by this app instance (factory scope — never a module-level global)."""
    if li_chao_tree is None:
        li_chao_tree = LiChaoTree()

    @app.post("/api/v1/lichao/add_line")
    async def api_lichao_add_line(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "m" not in body or "b" not in body:
            return JSONResponse({"error": "m and b are required"}, status_code=422)
        try:
            li_chao_tree.add_line(body["m"], body["b"])
        except LiChaoTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"m": body["m"], "b": body["b"], "num_lines": li_chao_tree.num_lines})

    @app.post("/api/v1/lichao/add_lines")
    async def api_lichao_add_lines(request: Request) -> JSONResponse:
        body = await request.json()
        lines = body.get("lines") if isinstance(body, dict) else None
        if not isinstance(lines, list) or not all(
                isinstance(p, (list, tuple)) and len(p) == 2 for p in lines):
            return JSONResponse({"error": "lines must be a list of [m, b] pairs"}, status_code=422)
        try:
            for m, b in lines:
                li_chao_tree.add_line(m, b)
        except LiChaoTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"added": len(lines), "num_lines": li_chao_tree.num_lines})

    @app.get("/api/v1/lichao/query")
    async def api_lichao_query(x: int = Query(...)) -> JSONResponse:
        try:
            v = li_chao_tree.query(x)
        except LiChaoTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"x": x, "value": v})

    @app.get("/api/v1/lichao/stats")
    async def api_lichao_stats() -> JSONResponse:
        return JSONResponse(li_chao_tree.stats())

    @app.delete("/api/v1/lichao/reset")
    async def api_lichao_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            li_chao_tree.reset(body.get("x_min"), body.get("x_max"), body.get("mode"))
        except LiChaoTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(li_chao_tree.stats())

    return li_chao_tree
