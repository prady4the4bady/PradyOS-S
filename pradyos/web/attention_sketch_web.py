"""Sovereign Frequency-Aware Attention HTTP routes (cognitive layer).

Exposes an :class:`~pradyos.core.attention_sketch.AttentionSketch` over REST. Routes
are registered onto the FastAPI ``app`` built by ``sovereign_web.create_app()`` via
:func:`register_attention_routes`, called *inside* the factory — the sketch lives
in factory scope (passed in, or created fresh per app), so there is no module-level
singleton.

Routes (mounted under ``/api/v1/attention``):
  POST   /api/v1/attention/attend   body ``{"tokens": [...]}`` — feed a token stream
  GET    /api/v1/attention/weight   ``?token=`` — normalized attention weight in [0,1]
  GET    /api/v1/attention/top      ``?k=`` — top-k ``[{token, weight}]`` (k ≥ 1)
  POST   /api/v1/attention/decay    apply one exponential-decay step
  GET    /api/v1/attention/stats    ``{total_tokens, unique_tracked, decay_steps, ...}``
  POST   /api/v1/attention/reset    clear to pristine state
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.core.attention_sketch import AttentionSketch, AttentionSketchError


def register_attention_routes(app: Any, sketch: Any | None = None) -> Any:
    """Register the /api/v1/attention routes on ``app``; return the sketch used.

    ``sketch`` defaults to a fresh :class:`AttentionSketch` owned by this app
    instance (factory scope — never a module-level global)."""
    if sketch is None:
        sketch = AttentionSketch()

    @app.post("/api/v1/attention/attend")
    async def api_attn_attend(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("tokens"), list):
            return JSONResponse({"error": "tokens (list) is required"}, status_code=422)
        try:
            sketch.attend(body["tokens"])
        except AttentionSketchError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"total_tokens": sketch.stats()["total_tokens"]})

    @app.get("/api/v1/attention/weight")
    async def api_attn_weight(token: str = Query(...)) -> JSONResponse:
        return JSONResponse({"token": token, "weight": sketch.weight(token)})

    @app.get("/api/v1/attention/top")
    async def api_attn_top(k: int = Query(10, ge=1)) -> JSONResponse:
        top = sketch.top_concepts(k)
        return JSONResponse({"top": [{"token": t, "weight": w} for t, w in top]})

    @app.post("/api/v1/attention/decay")
    async def api_attn_decay() -> JSONResponse:
        sketch.decay()
        return JSONResponse({"decay_steps": sketch.stats()["decay_steps"], "scale": sketch.stats()["scale"]})

    @app.get("/api/v1/attention/stats")
    async def api_attn_stats() -> JSONResponse:
        return JSONResponse(sketch.stats())

    @app.post("/api/v1/attention/reset")
    async def api_attn_reset() -> JSONResponse:
        sketch.reset()
        return JSONResponse(sketch.stats())

    return sketch
