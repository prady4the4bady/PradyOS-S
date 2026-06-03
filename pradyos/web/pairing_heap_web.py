"""Phase 150 — Sovereign Pairing Heap HTTP routes.

Exposes a :class:`~pradyos.core.pairing_heap.PairingHeap` over REST. Routes are registered onto
the FastAPI ``app`` built by ``sovereign_web.create_app()`` via :func:`register_pairingheap_routes`,
called *inside* the factory — the heap lives in factory scope (passed in, or created fresh per
app), so there is no module-level singleton. All routes are static (no path parameters), so none
can shadow another.

A non-numeric value, a bad/dead handle, an attempt to increase a key, or a pop from an empty heap
is a request error → **HTTP 422**. ``find_min`` is a benign query: on an empty heap it returns
``{"min": null, "size": 0}`` rather than erroring.

Routes (mounted under ``/api/v1/pairingheap``):
  POST   /api/v1/pairingheap/insert        body ``{"value"}`` — ``{handle, size, min}``
  GET    /api/v1/pairingheap/find_min       ``{min, size}``  (min may be null)
  POST   /api/v1/pairingheap/delete_min    pop the minimum — ``{min, size}`` (422 if empty)
  POST   /api/v1/pairingheap/decrease_key  body ``{"handle", "value"}`` — ``{handle, value, min, size}``
  GET    /api/v1/pairingheap/stats          ``{size, nodes, min}``
  DELETE /api/v1/pairingheap/reset          clear the heap
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.core.pairing_heap import PairingHeap, PairingHeapError


def register_pairingheap_routes(app: Any, pairing_heap: Any | None = None) -> Any:
    """Register the /api/v1/pairingheap routes on ``app``; return the heap used.

    ``pairing_heap`` defaults to a fresh empty :class:`PairingHeap` owned by this app instance
    (factory scope — never a module-level global)."""
    if pairing_heap is None:
        pairing_heap = PairingHeap()
    ph = pairing_heap

    @app.post("/api/v1/pairingheap/insert")
    async def api_ph_insert(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        try:
            handle = ph.insert(body["value"])
        except PairingHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"handle": handle, "size": ph.size, "min": ph.stats()["min"]})

    @app.get("/api/v1/pairingheap/find_min")
    async def api_ph_find_min() -> JSONResponse:
        s = ph.stats()
        return JSONResponse({"min": s["min"], "size": s["size"]})

    @app.post("/api/v1/pairingheap/delete_min")
    async def api_ph_delete_min() -> JSONResponse:
        try:
            value = ph.delete_min()
        except PairingHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"min": value, "size": ph.size})

    @app.post("/api/v1/pairingheap/decrease_key")
    async def api_ph_decrease_key(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "handle" not in body or "value" not in body:
            return JSONResponse({"error": "handle and value are required"}, status_code=422)
        try:
            ph.decrease_key(body["handle"], body["value"])
        except PairingHeapError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"handle": body["handle"], "value": body["value"],
                             "min": ph.stats()["min"], "size": ph.size})

    @app.get("/api/v1/pairingheap/stats")
    async def api_ph_stats() -> JSONResponse:
        return JSONResponse(ph.stats())

    @app.delete("/api/v1/pairingheap/reset")
    async def api_ph_reset() -> JSONResponse:
        ph.reset()
        return JSONResponse(ph.stats())

    return ph
