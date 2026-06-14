"""HTTP surface for REVERIE — the idle cognition loop (reflection + curiosity).

Registers ``/api/v1/reverie/*``: trigger a reflection, read recent insights, and
inspect stats. The engine is constructed with the live FORESIGHT engine + skill
library so a reflection reasons over the OS's real cognitive state.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query
from fastapi.responses import JSONResponse

from pradyos.reverie import Reverie


def register_reverie_routes(app: Any, reverie: Any | None = None) -> Any:
    """Register the ``/api/v1/reverie`` routes on ``app``; return the engine."""
    rev: Reverie = reverie if reverie is not None else Reverie()

    @app.post("/api/v1/reverie/reflect")
    async def api_reverie_reflect() -> JSONResponse:
        return JSONResponse(rev.reflect())

    @app.get("/api/v1/reverie/insights")
    async def api_reverie_insights(limit: int = Query(10)) -> JSONResponse:
        return JSONResponse({"insights": rev.insights(limit)})

    @app.get("/api/v1/reverie/stats")
    async def api_reverie_stats() -> JSONResponse:
        return JSONResponse(rev.stats())

    @app.delete("/api/v1/reverie/reset")
    async def api_reverie_reset() -> JSONResponse:
        rev.reset()
        return JSONResponse(rev.stats())

    return rev
