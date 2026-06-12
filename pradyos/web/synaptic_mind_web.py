"""HTTP surface for SYNAPTIC MIND — model management (Agent 6).

Registers ``/api/v1/synaptic/*``: register models, record benchmarks, set/promote
the default, and evaluate for upgrade proposals. Factory-scoped instance.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pradyos.synaptic_mind import SynapticError, SynapticMind
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_synaptic_routes(app: Any, synaptic: Any | None = None) -> Any:
    """Register the ``/api/v1/synaptic`` routes on ``app``; return the engine used."""
    mind: SynapticMind = synaptic if synaptic is not None else SynapticMind()

    @app.post("/api/v1/synaptic/model")
    async def api_synaptic_model(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "name" not in body:
            return JSONResponse({"error": "name is required"}, status_code=422)
        try:
            return JSONResponse(mind.register_model(body["name"], body.get("provider", "")))
        except SynapticError as exc:
            return _err(exc)

    @app.post("/api/v1/synaptic/benchmark")
    async def api_synaptic_benchmark(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "name" not in body or "score" not in body:
            return JSONResponse({"error": "name and score are required"}, status_code=422)
        try:
            return JSONResponse(mind.record_benchmark(body["name"], body["score"]))
        except SynapticError as exc:
            return _err(exc)

    @app.post("/api/v1/synaptic/default")
    async def api_synaptic_default(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "name" not in body:
            return JSONResponse({"error": "name is required"}, status_code=422)
        try:
            return JSONResponse(mind.set_default(body["name"]))
        except SynapticError as exc:
            return _err(exc)

    @app.post("/api/v1/synaptic/promote")
    async def api_synaptic_promote(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "name" not in body:
            return JSONResponse({"error": "name is required"}, status_code=422)
        try:
            return JSONResponse(mind.promote(body["name"]))
        except SynapticError as exc:
            return _err(exc)

    @app.get("/api/v1/synaptic/evaluate")
    async def api_synaptic_evaluate() -> JSONResponse:
        try:
            return JSONResponse(mind.evaluate())
        except SynapticError as exc:
            return _err(exc)

    @app.get("/api/v1/synaptic/models")
    async def api_synaptic_models() -> JSONResponse:
        return JSONResponse({"models": mind.models()})

    @app.get("/api/v1/synaptic/stats")
    async def api_synaptic_stats() -> JSONResponse:
        return JSONResponse(mind.stats())

    @app.delete("/api/v1/synaptic/reset")
    async def api_synaptic_reset() -> JSONResponse:
        mind.reset()
        return JSONResponse(mind.stats())

    return mind
