"""HTTP surface for CODEMAP — the agent's structural self-knowledge.

Registers ``/api/v1/codemap/*``: analyse Python source into a structural map,
then query modules, symbols, definitions, and dependency/importer edges.
Factory-scoped, fully local/deterministic (parses source, never runs it).
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.codemap import CodeMap, CodeMapError
from pradyos.web._responses import err_response as _err
from pradyos.web._responses import read_json as _json


def register_codemap_routes(app: Any, codemap: Any | None = None) -> Any:
    """Register the ``/api/v1/codemap`` routes on ``app``; return the map used."""
    cmap: CodeMap = codemap if codemap is not None else CodeMap()

    @app.post("/api/v1/codemap/analyze")
    async def api_codemap_analyze(request: Request) -> JSONResponse:
        body = await _json(request)
        if not isinstance(body, dict) or "module" not in body or "source" not in body:
            return JSONResponse({"error": "module and source are required"}, status_code=422)
        if not isinstance(body["source"], str):
            return JSONResponse({"error": "source must be a string"}, status_code=422)
        try:
            return JSONResponse(cmap.analyze(body["module"], body["source"]))
        except CodeMapError as exc:
            # All analyze failures are bad input (incl. parse errors, whose
            # message contains "<unknown>" — don't let that map to 404).
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.get("/api/v1/codemap/module")
    async def api_codemap_module(name: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse(cmap.module(name))
        except CodeMapError as exc:
            return _err(exc)

    @app.get("/api/v1/codemap/modules")
    async def api_codemap_modules() -> JSONResponse:
        return JSONResponse({"modules": cmap.modules()})

    @app.get("/api/v1/codemap/defines")
    async def api_codemap_defines(symbol: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse({"symbol": symbol, "definitions": cmap.defines(symbol)})
        except CodeMapError as exc:
            return _err(exc)

    @app.get("/api/v1/codemap/dependencies")
    async def api_codemap_dependencies(name: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse({"module": name, "dependencies": cmap.dependencies(name)})
        except CodeMapError as exc:
            return _err(exc)

    @app.get("/api/v1/codemap/importers")
    async def api_codemap_importers(target: str = Query(...)) -> JSONResponse:
        try:
            return JSONResponse({"target": target, "importers": cmap.importers(target)})
        except CodeMapError as exc:
            return _err(exc)

    @app.get("/api/v1/codemap/symbols")
    async def api_codemap_symbols(kind: str | None = Query(None)) -> JSONResponse:
        try:
            return JSONResponse({"symbols": cmap.symbols(kind)})
        except CodeMapError as exc:
            return _err(exc)

    @app.get("/api/v1/codemap/summary")
    async def api_codemap_summary() -> JSONResponse:
        return JSONResponse(cmap.summary())

    @app.delete("/api/v1/codemap/reset")
    async def api_codemap_reset() -> JSONResponse:
        cmap.reset()
        return JSONResponse(cmap.summary())

    return cmap
