"""HTTP surface for PRISM — creative artifact production (Agent PRISM).

Registers ``/api/v1/prism/*``: request an artifact, drive it through the
generation lifecycle, add variants, and browse the gallery. Factory-scoped.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.prism import Prism, PrismError
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_prism_routes(app: Any, prism: Any | None = None) -> Any:
    """Register the ``/api/v1/prism`` routes on ``app``; return the studio used."""
    studio: Prism = prism if prism is not None else Prism()

    @app.post("/api/v1/prism/request")
    async def api_prism_request(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or not all(k in body for k in ("id", "kind", "brief")):
            return JSONResponse({"error": "id, kind, brief are required"}, status_code=422)
        try:
            return JSONResponse(studio.request(body["id"], body["kind"], body["brief"]))
        except PrismError as exc:
            return _err(exc)

    @app.post("/api/v1/prism/start")
    async def api_prism_start(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body:
            return JSONResponse({"error": "id is required"}, status_code=422)
        try:
            return JSONResponse(studio.start(body["id"]))
        except PrismError as exc:
            return _err(exc)

    @app.post("/api/v1/prism/deliver")
    async def api_prism_deliver(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body or "output_ref" not in body:
            return JSONResponse({"error": "id and output_ref are required"}, status_code=422)
        try:
            return JSONResponse(studio.deliver(body["id"], body["output_ref"]))
        except PrismError as exc:
            return _err(exc)

    @app.post("/api/v1/prism/variant")
    async def api_prism_variant(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body or "output_ref" not in body:
            return JSONResponse({"error": "id and output_ref are required"}, status_code=422)
        try:
            return JSONResponse(studio.add_variant(body["id"], body["output_ref"]))
        except PrismError as exc:
            return _err(exc)

    @app.post("/api/v1/prism/fail")
    async def api_prism_fail(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "id" not in body:
            return JSONResponse({"error": "id is required"}, status_code=422)
        try:
            return JSONResponse(studio.fail(body["id"], body.get("reason", "")))
        except PrismError as exc:
            return _err(exc)

    @app.get("/api/v1/prism/artifact")
    async def api_prism_artifact(id: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(studio.artifact(id))
        except PrismError as exc:
            return _err(exc)

    @app.get("/api/v1/prism/gallery")
    async def api_prism_gallery(kind: str | None = Query(None)) -> JSONResponse:
        try:
            return JSONResponse({"gallery": studio.gallery(kind=kind)})
        except PrismError as exc:
            return _err(exc)

    @app.get("/api/v1/prism/stats")
    async def api_prism_stats() -> JSONResponse:
        return JSONResponse(studio.stats())

    @app.delete("/api/v1/prism/reset")
    async def api_prism_reset() -> JSONResponse:
        studio.reset()
        return JSONResponse(studio.stats())

    return studio
