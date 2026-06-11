"""Phase 105 — Sovereign Q-Digest HTTP routes.

Exposes a :class:`~pradyos.core.q_digest.QDigest` over REST. Routes are
registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_qdigest_routes`, called *inside* the factory — the digest lives
in factory scope (passed in, or created fresh per app), so there is no
module-level singleton. All routes are static (no path parameters), so none can
shadow another.

Routes (mounted under ``/api/v1/qdigest``):
  POST   /api/v1/qdigest/add       body ``{"value": v, "count"?: c}`` — add occurrences
  GET    /api/v1/qdigest/quantile  ``?q=`` — value v with ≈ q·n elements ≤ v (q in (0,1))
  POST   /api/v1/qdigest/merge     body ``{"values": [...]}`` — build a temp digest, merge in
  GET    /api/v1/qdigest/stats     ``{compression_factor, value_range, total_count, num_nodes, theoretical_max_nodes}``
  POST   /api/v1/qdigest/reset     body ``{"compression_factor"?, "value_range"?, "seed"?}`` — clear / reconfigure
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.q_digest import QDigest, QDigestError


def register_qdigest_routes(app: Any, qdigest: Any | None = None) -> Any:
    """Register the /api/v1/qdigest routes on ``app``; return the digest used.

    ``qdigest`` defaults to a fresh :class:`QDigest` owned by this app instance
    (factory scope — never a module-level global)."""
    if qdigest is None:
        qdigest = QDigest()

    @app.post("/api/v1/qdigest/add")
    async def api_qd_add(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or "value" not in body:
            return JSONResponse({"error": "value is required"}, status_code=422)
        count = body.get("count", 1)
        try:
            qdigest.add(body["value"], count)
        except QDigestError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"value": body["value"], "count": count, "total": qdigest.total_count})

    @app.get("/api/v1/qdigest/quantile")
    async def api_qd_quantile(q: float = Query(gt=0.0, lt=1.0)) -> JSONResponse:
        try:
            value = qdigest.quantile(q)
        except QDigestError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse({"q": q, "value": value})

    @app.post("/api/v1/qdigest/merge")
    async def api_qd_merge(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("values"), list):
            return JSONResponse({"error": "values list is required"}, status_code=422)
        temp = QDigest(
            compression_factor=qdigest.compression_factor,
            value_range=qdigest.value_range,
            seed=qdigest.seed,
        )
        try:
            for v in body["values"]:
                temp.add(v)
            qdigest.merge(temp)
        except QDigestError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(qdigest.stats())

    @app.get("/api/v1/qdigest/stats")
    async def api_qd_stats() -> JSONResponse:
        return JSONResponse(qdigest.stats())

    @app.post("/api/v1/qdigest/reset")
    async def api_qd_reset(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            qdigest.reset(body.get("compression_factor"), body.get("value_range"), body.get("seed"))
        except QDigestError as exc:
            return JSONResponse({"error": str(exc.detail)}, status_code=422)
        return JSONResponse(qdigest.stats())

    return qdigest
