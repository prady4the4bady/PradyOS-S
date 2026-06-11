"""Phase 145 — Sovereign Cartesian Tree HTTP routes.

Exposes a :class:`~pradyos.core.cartesian_tree.CartesianTree` over REST. Routes are registered
onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_cartesiantree_routes`, called *inside* the factory — the tree lives in factory
scope (passed in, or created fresh per app), so there is no module-level singleton. All routes
are static (no path parameters), so none can shadow another.

A non-numeric value or out-of-range ``[lo, hi]`` is a request error → **HTTP 422** (the range
query uses the ``Query(ge=0)`` idiom; the `lo ≤ hi < n` rule is caught from the core).

Routes (mounted under ``/api/v1/cartesiantree``):
  POST   /api/v1/cartesiantree/build      body ``{"values": [...]}`` — returns stats
  GET    /api/v1/cartesiantree/range_min  query ``?lo=&hi=`` — ``{lo, hi, min, argmin}``
  GET    /api/v1/cartesiantree/structure   ``{root, parent, left, right}``
  GET    /api/v1/cartesiantree/stats        ``{size, height, root_index}``
  DELETE /api/v1/cartesiantree/reset        (no body) — clear
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.cartesian_tree import CartesianTree, CartesianTreeError


def register_cartesiantree_routes(app: Any, cartesian_tree: Any | None = None) -> Any:
    """Register the /api/v1/cartesiantree routes on ``app``; return the tree used.

    ``cartesian_tree`` defaults to a fresh (empty) :class:`CartesianTree` owned by this app
    instance (factory scope — never a module-level global)."""
    if cartesian_tree is None:
        cartesian_tree = CartesianTree()

    @app.post("/api/v1/cartesiantree/build")
    async def api_ct_build(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("values"), list):
            return JSONResponse({"error": "values list is required"}, status_code=422)
        try:
            cartesian_tree.build(body["values"])
        except CartesianTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(cartesian_tree.stats())

    @app.get("/api/v1/cartesiantree/range_min")
    async def api_ct_range_min(
        lo: int = Query(..., ge=0), hi: int = Query(..., ge=0)
    ) -> JSONResponse:
        try:
            mn = cartesian_tree.range_min(lo, hi)
            am = cartesian_tree.range_argmin(lo, hi)
        except CartesianTreeError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"lo": lo, "hi": hi, "min": mn, "argmin": am})

    @app.get("/api/v1/cartesiantree/structure")
    async def api_ct_structure() -> JSONResponse:
        return JSONResponse(cartesian_tree.structure())

    @app.get("/api/v1/cartesiantree/stats")
    async def api_ct_stats() -> JSONResponse:
        return JSONResponse(cartesian_tree.stats())

    @app.delete("/api/v1/cartesiantree/reset")
    async def api_ct_reset() -> JSONResponse:
        cartesian_tree.reset()
        return JSONResponse(cartesian_tree.stats())

    return cartesian_tree
