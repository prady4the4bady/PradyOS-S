"""Phase 161 — Sovereign Binary Lifting HTTP routes.

Exposes a :class:`~pradyos.core.binary_lifting.BinaryLifting` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_binarylifting_routes`,
called *inside* the factory — the structure lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so none
can shadow another.

A malformed parent array, an out-of-range node, or a negative ``k`` is a request error →
**HTTP 422**. ``lca`` / ``kth_ancestor`` return ``null`` when there is no such node.

Routes (mounted under ``/api/v1/binarylifting``):
  POST   /api/v1/binarylifting/build         body ``{"parents": [...]}`` — rebuild, returns stats
  GET    /api/v1/binarylifting/lca           query ``?u=&v=`` — ``{u, v, lca}``  (lca may be null)
  GET    /api/v1/binarylifting/kth_ancestor  query ``?v=&k=`` — ``{v, k, ancestor}``  (may be null)
  GET    /api/v1/binarylifting/depth         query ``?v=`` — ``{v, depth}``
  GET    /api/v1/binarylifting/is_ancestor   query ``?u=&v=`` — ``{u, v, is_ancestor}``
  GET    /api/v1/binarylifting/stats          ``{size, levels, max_depth, num_roots}``
  DELETE /api/v1/binarylifting/reset          discard the tree
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.binary_lifting import BinaryLifting, BinaryLiftingError


def register_binarylifting_routes(app: Any, binary_lifting: Any | None = None) -> Any:
    """Register the /api/v1/binarylifting routes on ``app``; return the structure used.

    ``binary_lifting`` defaults to a fresh empty :class:`BinaryLifting` owned by this app instance
    (factory scope — never a module-level global)."""
    if binary_lifting is None:
        binary_lifting = BinaryLifting()
    bl = binary_lifting

    @app.post("/api/v1/binarylifting/build")
    async def api_bl_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "parents" not in body:
            return JSONResponse({"error": "parents is required"}, status_code=422)
        try:
            bl.build(body["parents"])
        except BinaryLiftingError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(bl.stats())

    @app.get("/api/v1/binarylifting/lca")
    async def api_bl_lca(u: int = Query(..., ge=0), v: int = Query(..., ge=0)) -> JSONResponse:
        try:
            ans = bl.lca(u, v)
        except BinaryLiftingError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"u": u, "v": v, "lca": ans})

    @app.get("/api/v1/binarylifting/kth_ancestor")
    async def api_bl_kth(v: int = Query(..., ge=0), k: int = Query(..., ge=0)) -> JSONResponse:
        try:
            ans = bl.kth_ancestor(v, k)
        except BinaryLiftingError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"v": v, "k": k, "ancestor": ans})

    @app.get("/api/v1/binarylifting/depth")
    async def api_bl_depth(v: int = Query(..., ge=0)) -> JSONResponse:
        try:
            d = bl.depth(v)
        except BinaryLiftingError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"v": v, "depth": d})

    @app.get("/api/v1/binarylifting/is_ancestor")
    async def api_bl_is_ancestor(
        u: int = Query(..., ge=0), v: int = Query(..., ge=0)
    ) -> JSONResponse:
        try:
            ans = bl.is_ancestor(u, v)
        except BinaryLiftingError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"u": u, "v": v, "is_ancestor": ans})

    @app.get("/api/v1/binarylifting/stats")
    async def api_bl_stats() -> JSONResponse:
        return JSONResponse(bl.stats())

    @app.delete("/api/v1/binarylifting/reset")
    async def api_bl_reset() -> JSONResponse:
        bl.reset()
        return JSONResponse(bl.stats())

    return bl
