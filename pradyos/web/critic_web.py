"""HTTP surface for CRITIC — the adversarial critic ensemble (autonomy L4).

Registers ``/api/v1/critic/*``: judge a proposal (diff, edit, or goal) across the
critic panel, list the active critics, and read stats. Factory-scoped, offline.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.critic import CriticEnsemble
from pradyos.web._responses import read_json as _json


def register_critic_routes(app: Any, ensemble: Any | None = None) -> Any:
    """Register the ``/api/v1/critic`` routes on ``app``; return the ensemble."""
    panel: CriticEnsemble = ensemble if ensemble is not None else CriticEnsemble()

    @app.post("/api/v1/critic/judge")
    async def api_critic_judge(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "proposal" not in body:
            return JSONResponse({"error": "proposal is required"}, status_code=422)
        return JSONResponse(panel.judge(str(body["proposal"])))

    @app.get("/api/v1/critic/critics")
    async def api_critic_critics() -> JSONResponse:
        return JSONResponse({"critics": panel.critics()})

    @app.get("/api/v1/critic/stats")
    async def api_critic_stats() -> JSONResponse:
        return JSONResponse(panel.stats())

    return panel
