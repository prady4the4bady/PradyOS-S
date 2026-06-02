"""Phase 116 — Sovereign TinyLFU HTTP routes.

Exposes a :class:`~pradyos.core.tiny_lfu.TinyLFU` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_tinylfu_routes`, called *inside* the factory — the sketch lives in
factory scope (passed in, or created fresh per app), so there is no module-level
singleton. All routes are static (no path parameters), so none can shadow another.

Routes (mounted under ``/api/v1/tinylfu``):
  POST   /api/v1/tinylfu/add       body ``{"key": x}`` — record an access
  GET    /api/v1/tinylfu/estimate  ``?key=`` — approximate (aging) frequency
  POST   /api/v1/tinylfu/admit     body ``{"candidate": x, "victim": y}`` — admission decision
  GET    /api/v1/tinylfu/stats     ``{sample_size, width, depth, doorkeeper_bits, total, accesses_since_reset, resets, seed}``
  DELETE /api/v1/tinylfu/reset     body ``{"sample_size"?, "width"?, "depth"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.tiny_lfu import TinyLFU, TinyLFUError


def register_tinylfu_routes(app: Any, tiny_lfu: Any | None = None) -> Any:
    """Register the /api/v1/tinylfu routes on ``app``; return the sketch used.

    ``tiny_lfu`` defaults to a fresh :class:`TinyLFU` owned by this app instance
    (factory scope — never a module-level global)."""
    if tiny_lfu is None:
        tiny_lfu = TinyLFU()

    @app.post("/api/v1/tinylfu/add")
    async def api_tlfu_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "key" not in body:
            return JSONResponse({"error": "key is required"}, status_code=422)
        tiny_lfu.add(str(body["key"]))
        return JSONResponse({"key": str(body["key"]), "total": tiny_lfu.total})

    @app.get("/api/v1/tinylfu/estimate")
    async def api_tlfu_estimate(key: str) -> JSONResponse:
        return JSONResponse({"key": key, "estimate": tiny_lfu.estimate(key)})

    @app.post("/api/v1/tinylfu/admit")
    async def api_tlfu_admit(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "candidate" not in body or "victim" not in body:
            return JSONResponse({"error": "candidate and victim are required"}, status_code=422)
        cand, vic = str(body["candidate"]), str(body["victim"])
        return JSONResponse({"candidate": cand, "victim": vic, "admit": tiny_lfu.admit(cand, vic)})

    @app.get("/api/v1/tinylfu/stats")
    async def api_tlfu_stats() -> JSONResponse:
        return JSONResponse(tiny_lfu.stats())

    @app.delete("/api/v1/tinylfu/reset")
    async def api_tlfu_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            tiny_lfu.reset(body.get("sample_size"), body.get("width"),
                           body.get("depth"), body.get("seed"))
        except TinyLFUError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(tiny_lfu.stats())

    return tiny_lfu
