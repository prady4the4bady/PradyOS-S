"""HTTP surface for CHRONICLE SAGE — institutional memory (Agent 7).

Registers ``/api/v1/chronicle/*``: record entries, query by type/tag, get the
latest, and read the "what changed" digest. Factory-scoped instance.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.chronicle_sage import ChronicleError, ChronicleSage
from pradyos.web._responses import read_json as _json


def register_chronicle_routes(app: Any, chronicle: Any | None = None) -> Any:
    """Register the ``/api/v1/chronicle`` routes on ``app``; return the ledger used."""
    sage: ChronicleSage = chronicle if chronicle is not None else ChronicleSage()

    @app.post("/api/v1/chronicle/record")
    async def api_chronicle_record(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "type" not in body or "title" not in body:
            return JSONResponse({"error": "type and title are required"}, status_code=422)
        tags = body.get("tags")
        if tags is not None and not isinstance(tags, list):
            return JSONResponse({"error": "tags must be a list"}, status_code=422)
        try:
            return JSONResponse(
                sage.record(body["type"], body["title"], body.get("body", ""), tags)
            )
        except ChronicleError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/chronicle/entries")
    async def api_chronicle_entries(
        type: str | None = Query(None),
        tag: str | None = Query(None),
        limit: int = Query(50),
    ) -> JSONResponse:
        try:
            return JSONResponse({"entries": sage.entries(entry_type=type, tag=tag, limit=limit)})
        except ChronicleError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/chronicle/latest")
    async def api_chronicle_latest(type: str | None = Query(None)) -> JSONResponse:
        try:
            return JSONResponse({"latest": sage.latest(entry_type=type)})
        except ChronicleError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/chronicle/digest")
    async def api_chronicle_digest(limit: int = Query(20)) -> JSONResponse:
        return JSONResponse(sage.digest(limit=limit))

    @app.get("/api/v1/chronicle/stats")
    async def api_chronicle_stats() -> JSONResponse:
        return JSONResponse(sage.stats())

    @app.delete("/api/v1/chronicle/reset")
    async def api_chronicle_reset() -> JSONResponse:
        sage.reset()
        return JSONResponse(sage.stats())

    return sage
