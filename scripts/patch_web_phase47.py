"""Patch sovereign_web.py for Phase 47: MemoryGraph import + 5 endpoints.

DEVIATION: Phase 17 already owns /api/v1/graph/* routes with a different
module (pradyos.core.memorygraph using kind/label/attributes). To avoid
breaking Phase 17 tests, Phase 47 uses /api/v1/memgraph/* prefix.
"""
from pathlib import Path

TARGET = Path("pradyos/sovereign_web.py")
src = TARGET.read_text(encoding="utf-8")

# ── 1. Add import ──────────────────────────────────────────────────────────────
OLD_IMPORT = "from pradyos.core.web_agent import WebAgent  # Phase 46"
NEW_IMPORT = (
    "from pradyos.core.web_agent import WebAgent  # Phase 46\n"
    "from pradyos.core.memory_graph import MemoryGraph as Phase47MemoryGraph  # Phase 47"
)
if "Phase47MemoryGraph" not in src:
    assert OLD_IMPORT in src, "Could not find Phase 46 import anchor"
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)

# ── 2. Add 5 endpoints before `    return app` ────────────────────────────────
NEW_ENDPOINTS = '''
    @app.get("/api/v1/memgraph/nodes")
    async def api_memgraph_nodes_list() -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"nodes": [], "count": 0})
        return JSONResponse({
            "nodes": [n.to_dict() for n in memory_graph._nodes.values()],
            "count": memory_graph.node_count(),
        })

    @app.post("/api/v1/memgraph/nodes")
    async def api_memgraph_nodes_add(request: Request) -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"error": "no memory graph configured"}, status_code=400)
        body = await request.json()
        if "name" not in body:
            return JSONResponse({"error": "missing 'name' key"}, status_code=400)
        node = memory_graph.add_node(
            name=str(body["name"]),
            metadata=body.get("metadata"),
        )
        return JSONResponse(node.to_dict())

    @app.post("/api/v1/memgraph/edges")
    async def api_memgraph_edges_add(request: Request) -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"error": "no memory graph configured"}, status_code=400)
        body = await request.json()
        for key in ("src", "dst", "relation"):
            if key not in body:
                return JSONResponse(
                    {"error": f"missing required key: {key}"},
                    status_code=400,
                )
        edge = memory_graph.add_edge(
            src=str(body["src"]),
            dst=str(body["dst"]),
            relation=str(body["relation"]),
            weight=float(body.get("weight", 1.0)),
        )
        return JSONResponse(edge.to_dict())

    @app.get("/api/v1/memgraph/neighbors/{name}")
    async def api_memgraph_neighbors(name: str, request: Request) -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"name": name, "neighbors": []})
        relation = request.query_params.get("relation")
        neighbors = memory_graph.get_neighbors(name, relation=relation)
        return JSONResponse({
            "name": name,
            "neighbors": [n.to_dict() for n in neighbors],
        })

    @app.get("/api/v1/memgraph/path")
    async def api_memgraph_path(src: str, dst: str) -> JSONResponse:
        if memory_graph is None:
            return JSONResponse({"src": src, "dst": dst, "path": None})
        path = memory_graph.shortest_path(src, dst)
        return JSONResponse({"src": src, "dst": dst, "path": path})

'''

if "/api/v1/memgraph/nodes" not in src:
    assert "    return app" in src, "Could not find 'return app' anchor"
    src = src.replace("    return app", NEW_ENDPOINTS + "    return app", 1)

TARGET.write_text(src, encoding="utf-8")
print("Patch applied successfully.")
