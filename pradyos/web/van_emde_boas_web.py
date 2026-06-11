"""Phase 152 — Sovereign van Emde Boas Tree HTTP routes.

Exposes a :class:`~pradyos.core.van_emde_boas.VanEmdeBoas` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_veb_routes`, called
*inside* the factory — the set lives in factory scope (passed in, or created fresh per app), so
there is no module-level singleton. All routes are static (no path parameters), so none can shadow
another.

A non-integer value or a value outside ``[0, universe)`` is a request error → **HTTP 422** (query
values use the ``Query(ge=0)`` idiom; the upper bound is caught from the core). ``successor`` /
``predecessor`` return ``null`` when there is no such element.

Routes (mounted under ``/api/v1/veb``):
  POST   /api/v1/veb/insert       body ``{"value"}`` — ``{value, added, size}``
  POST   /api/v1/veb/delete       body ``{"value"}`` — ``{value, deleted, size}``
  GET    /api/v1/veb/member       query ``?value=`` — ``{value, member}``
  GET    /api/v1/veb/successor    query ``?value=`` — ``{value, successor}``  (may be null)
  GET    /api/v1/veb/predecessor  query ``?value=`` — ``{value, predecessor}``  (may be null)
  GET    /api/v1/veb/stats         ``{size, universe, min, max}``
  DELETE /api/v1/veb/reset         empty the set
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.van_emde_boas import VanEmdeBoas, VanEmdeBoasError


def register_veb_routes(app: Any, van_emde_boas: Any | None = None) -> Any:
    """Register the /api/v1/veb routes on ``app``; return the set used.

    ``van_emde_boas`` defaults to a fresh :class:`VanEmdeBoas` over ``[0, 65536)`` owned by this
    app instance (factory scope — never a module-level global)."""
    if van_emde_boas is None:
        van_emde_boas = VanEmdeBoas()
    veb = van_emde_boas

    @app.post("/api/v1/veb/insert")
    async def api_veb_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            added = veb.insert(body["value"])
        except VanEmdeBoasError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "added": added, "size": veb.size})

    @app.post("/api/v1/veb/delete")
    async def api_veb_delete(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            deleted = veb.delete(body["value"])
        except VanEmdeBoasError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "deleted": deleted, "size": veb.size})

    @app.get("/api/v1/veb/member")
    async def api_veb_member(value: int = Query(..., ge=0)) -> JSONResponse:
        try:
            present = veb.member(value)
        except VanEmdeBoasError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": value, "member": present})

    @app.get("/api/v1/veb/successor")
    async def api_veb_successor(value: int = Query(..., ge=0)) -> JSONResponse:
        try:
            s = veb.successor(value)
        except VanEmdeBoasError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": value, "successor": s})

    @app.get("/api/v1/veb/predecessor")
    async def api_veb_predecessor(value: int = Query(..., ge=0)) -> JSONResponse:
        try:
            p = veb.predecessor(value)
        except VanEmdeBoasError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": value, "predecessor": p})

    @app.get("/api/v1/veb/stats")
    async def api_veb_stats() -> JSONResponse:
        return JSONResponse(veb.stats())

    @app.delete("/api/v1/veb/reset")
    async def api_veb_reset() -> JSONResponse:
        veb.reset()
        return JSONResponse(veb.stats())

    return veb
