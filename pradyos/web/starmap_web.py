"""HTTP surface for STARMAP — the knowledge-graph plane (Plane 6).

Registers ``/api/v1/starmap/*`` on the Sovereign Web app: add entities and
relations, then query neighbors, shortest paths, reachability, and causal
chains. The graph instance is factory-scoped (one per app), never a global.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from pradyos.starmap import KnowledgeGraph, StarmapError, UnknownNodeError


def register_starmap_routes(app: Any, starmap: Any | None = None) -> Any:
    """Register the ``/api/v1/starmap`` routes on ``app``; return the graph used."""
    graph: KnowledgeGraph = starmap if starmap is not None else KnowledgeGraph()

    @app.post("/api/v1/starmap/node")
    async def api_starmap_add_node(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=422)
        if not isinstance(body, dict) or "id" not in body or "type" not in body:
            return JSONResponse({"error": "id and type are required"}, status_code=422)
        attrs = body.get("attrs") or {}
        if not isinstance(attrs, dict):
            return JSONResponse({"error": "attrs must be an object"}, status_code=422)
        try:
            node = graph.add_node(body["id"], body["type"], **attrs)
        except StarmapError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(node.to_dict())

    @app.post("/api/v1/starmap/edge")
    async def api_starmap_add_edge(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=422)
        if not isinstance(body, dict) or not all(k in body for k in ("src", "rel", "dst")):
            return JSONResponse({"error": "src, rel, dst are required"}, status_code=422)
        attrs = body.get("attrs") or {}
        if not isinstance(attrs, dict):
            return JSONResponse({"error": "attrs must be an object"}, status_code=422)
        create_missing = body.get("create_missing", False)
        if not isinstance(create_missing, bool):
            return JSONResponse({"error": "create_missing must be a boolean"}, status_code=422)
        try:
            edge = graph.add_edge(
                body["src"],
                body["rel"],
                body["dst"],
                create_missing=create_missing,
                **attrs,
            )
        except UnknownNodeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except StarmapError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse(edge.to_dict())

    @app.get("/api/v1/starmap/nodes")
    async def api_starmap_nodes(type: str | None = Query(None)) -> JSONResponse:
        return JSONResponse({"nodes": [n.to_dict() for n in graph.nodes(type)]})

    @app.get("/api/v1/starmap/neighbors")
    async def api_starmap_neighbors(
        node_id: str = Query(...),
        rel: str | None = Query(None),
        direction: str = Query("out"),
    ) -> JSONResponse:
        try:
            result = graph.neighbors(node_id, rel=rel, direction=direction)
        except UnknownNodeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except StarmapError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"node": node_id, "neighbors": result})

    @app.get("/api/v1/starmap/path")
    async def api_starmap_path(
        src: str = Query(...),
        dst: str = Query(...),
        rel: str | None = Query(None),
        max_hops: int = Query(6),
    ) -> JSONResponse:
        try:
            p = graph.path(src, dst, rel=rel, max_hops=max_hops)
        except UnknownNodeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except StarmapError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"src": src, "dst": dst, "path": p, "found": p is not None})

    @app.get("/api/v1/starmap/reachable")
    async def api_starmap_reachable(
        src: str = Query(...),
        rel: str | None = Query(None),
        max_hops: int = Query(6),
    ) -> JSONResponse:
        try:
            r = graph.reachable(src, rel=rel, max_hops=max_hops)
        except UnknownNodeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except StarmapError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"src": src, "reachable": sorted(r)})

    @app.get("/api/v1/starmap/causal")
    async def api_starmap_causal(
        src: str = Query(...),
        rel: str = Query(...),
        max_hops: int = Query(6),
    ) -> JSONResponse:
        try:
            chain = graph.causal_chain(src, rel, max_hops=max_hops)
        except UnknownNodeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except StarmapError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        return JSONResponse({"src": src, "rel": rel, "chain": chain})

    @app.get("/api/v1/starmap/stats")
    async def api_starmap_stats() -> JSONResponse:
        return JSONResponse(graph.stats())

    @app.delete("/api/v1/starmap/reset")
    async def api_starmap_reset() -> JSONResponse:
        graph.reset()
        return JSONResponse(graph.stats())

    return graph
