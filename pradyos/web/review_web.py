"""HTTP surface for the REVIEW GATE — vet self-modifications.

Registers ``/api/v1/review/*``: assess a proposed code change through the
deterministic review panel, then inspect prior reviews. Factory-scoped,
fully local/deterministic (parses source, never runs it).
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.review import ReviewError, ReviewGate
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_review_routes(app: Any, review: Any | None = None) -> Any:
    """Register the ``/api/v1/review`` routes on ``app``; return the gate used."""
    gate: ReviewGate = review if review is not None else ReviewGate()

    @app.post("/api/v1/review/assess")
    async def api_review_assess(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "path" not in body or "after" not in body:
            return JSONResponse({"error": "path and after are required"}, status_code=422)
        if not isinstance(body["after"], str):
            return JSONResponse({"error": "after must be a string"}, status_code=422)
        before = body.get("before", "")
        if not isinstance(before, str):
            return JSONResponse({"error": "before must be a string"}, status_code=422)
        try:
            return JSONResponse(gate.assess(body["path"], body["after"], before))
        except ReviewError as exc:
            return _err(exc)

    @app.get("/api/v1/review/review")
    async def api_review_get(seq: int = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(gate.review(seq))
        except ReviewError as exc:
            return _err(exc)

    @app.get("/api/v1/review/reviews")
    async def api_review_list(limit: int = Query(20)) -> JSONResponse:
        try:
            return JSONResponse({"reviews": gate.reviews(limit=limit)})
        except ReviewError as exc:
            return _err(exc)

    @app.get("/api/v1/review/stats")
    async def api_review_stats() -> JSONResponse:
        return JSONResponse(gate.stats())

    @app.delete("/api/v1/review/reset")
    async def api_review_reset() -> JSONResponse:
        gate.reset()
        return JSONResponse(gate.stats())

    return gate
