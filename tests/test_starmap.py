"""STARMAP knowledge-graph tests — traversals checked against ground truth.

A small fixed graph models the blueprint's causal pattern:
    [oracle] --proposed--> [projectX] --resulted_in--> [outcomeOk]
    [projectX] --depends_on--> [redis]
    [helios] --proposed--> [projectY] --resulted_in--> [outcomeBad]
    [projectY] --depends_on--> [redis]
"""

from __future__ import annotations

import threading

import pytest

from pradyos.starmap import KnowledgeGraph, StarmapError, UnknownNodeError


def _g() -> KnowledgeGraph:
    g = KnowledgeGraph()
    for nid, ntype in [
        ("oracle", "agent"),
        ("helios", "agent"),
        ("projectX", "project"),
        ("projectY", "project"),
        ("outcomeOk", "outcome"),
        ("outcomeBad", "outcome"),
        ("redis", "service"),
    ]:
        g.add_node(nid, ntype)
    g.add_edge("oracle", "proposed", "projectX")
    g.add_edge("projectX", "resulted_in", "outcomeOk")
    g.add_edge("projectX", "depends_on", "redis")
    g.add_edge("helios", "proposed", "projectY")
    g.add_edge("projectY", "resulted_in", "outcomeBad")
    g.add_edge("projectY", "depends_on", "redis")
    return g


# ── nodes & edges ─────────────────────────────────────────────────────────────


def test_add_node_merges_attrs():
    g = KnowledgeGraph()
    g.add_node("a", "agent", role="scout")
    g.add_node("a", "agent", tier="prime")
    n = g.get_node("a")
    assert n.attrs == {"role": "scout", "tier": "prime"} and n.type == "agent"


def test_nodes_filter_by_type():
    g = _g()
    assert sorted(n.id for n in g.nodes("project")) == ["projectX", "projectY"]
    assert len(g.nodes()) == 7


def test_edges_filter_by_rel():
    g = _g()
    proposed = {(e.src, e.dst) for e in g.edges("proposed")}
    assert proposed == {("oracle", "projectX"), ("helios", "projectY")}


def test_add_edge_unknown_node_raises():
    g = KnowledgeGraph()
    g.add_node("a", "agent")
    with pytest.raises(UnknownNodeError):
        g.add_edge("a", "rel", "ghost")


def test_add_edge_create_missing():
    g = KnowledgeGraph()
    g.add_node("a", "agent")
    g.add_edge("a", "rel", "ghost", create_missing=True)
    assert g.has_node("ghost") and g.get_node("ghost").type == "unknown"


@pytest.mark.parametrize("bad", [("", "t"), ("id", "")])
def test_node_validation(bad):
    g = KnowledgeGraph()
    with pytest.raises(StarmapError):
        g.add_node(bad[0], bad[1])


# ── neighbors ─────────────────────────────────────────────────────────────────


def test_neighbors_out_in_both():
    g = _g()
    assert sorted(g.neighbors("projectX", direction="out")) == ["outcomeOk", "redis"]
    assert g.neighbors("projectX", direction="in") == ["oracle"]
    assert sorted(g.neighbors("projectX", direction="both")) == ["oracle", "outcomeOk", "redis"]


def test_neighbors_filter_by_rel():
    g = _g()
    assert g.neighbors("projectX", rel="resulted_in") == ["outcomeOk"]
    assert g.neighbors("redis", rel="depends_on", direction="in") == ["projectX", "projectY"]


def test_neighbors_unknown_raises():
    g = _g()
    with pytest.raises(UnknownNodeError):
        g.neighbors("nope")


# ── path / reachable (multi-hop) ──────────────────────────────────────────────


def test_path_multihop():
    g = _g()
    assert g.path("oracle", "outcomeOk") == ["oracle", "projectX", "outcomeOk"]


def test_path_none_when_unreachable():
    g = _g()
    # outcomeOk has no outgoing edges → nothing reaches helios from it.
    assert g.path("outcomeOk", "helios") is None


def test_path_respects_max_hops():
    g = _g()
    assert g.path("oracle", "outcomeOk", max_hops=1) is None
    assert g.path("oracle", "outcomeOk", max_hops=2) == ["oracle", "projectX", "outcomeOk"]


def test_path_rel_filter():
    g = _g()
    # following only 'proposed' can't reach the outcome (needs resulted_in).
    assert g.path("oracle", "outcomeOk", rel="proposed") is None


def test_reachable_set():
    g = _g()
    assert g.reachable("oracle") == {"projectX", "outcomeOk", "redis"}
    assert g.reachable("oracle", max_hops=1) == {"projectX"}


def test_reachable_via_shared_service_is_directional():
    g = _g()
    # redis is a sink (only inbound depends_on) → nothing reachable from it.
    assert g.reachable("redis") == set()


# ── causal chain ──────────────────────────────────────────────────────────────


def test_causal_chain():
    g = KnowledgeGraph()
    for i in range(5):
        g.add_node(f"n{i}", "step")
    for i in range(4):
        g.add_edge(f"n{i}", "leads_to", f"n{i + 1}")
    assert g.causal_chain("n0", "leads_to") == ["n0", "n1", "n2", "n3", "n4"]


def test_causal_chain_stops_and_is_cycle_safe():
    g = _g()
    assert g.causal_chain("projectX", "resulted_in") == ["projectX", "outcomeOk"]
    # cycle must not loop forever
    c = KnowledgeGraph()
    c.add_node("a", "x")
    c.add_node("b", "x")
    c.add_edge("a", "r", "b")
    c.add_edge("b", "r", "a")
    assert c.causal_chain("a", "r") == ["a", "b"]


# ── subgraph / degree / stats / remove / reset ────────────────────────────────


def test_subgraph_induced():
    g = _g()
    sg = g.subgraph(["oracle", "projectX", "outcomeOk", "ghost"])
    assert sorted(n["id"] for n in sg["nodes"]) == ["oracle", "outcomeOk", "projectX"]
    rels = {(e["src"], e["rel"], e["dst"]) for e in sg["edges"]}
    assert rels == {("oracle", "proposed", "projectX"), ("projectX", "resulted_in", "outcomeOk")}


def test_degree_and_stats():
    g = _g()
    assert g.degree("projectX") == {"out": 2, "in": 1}
    s = g.stats()
    assert s["nodes"] == 7 and s["edges"] == 6
    assert s["node_types"]["project"] == 2
    assert s["relations"]["depends_on"] == 2


def test_remove_node_cleans_edges():
    g = _g()
    assert g.remove_node("projectX") is True
    assert not g.has_node("projectX")
    # edges that touched projectX are gone
    assert all("projectX" not in (e.src, e.dst) for e in g.edges())
    assert g.neighbors("redis", direction="in") == ["projectY"]


def test_remove_edge():
    g = _g()
    assert g.remove_edge("projectX", "depends_on", "redis") is True
    assert g.neighbors("projectX", rel="depends_on") == []
    assert g.remove_edge("projectX", "depends_on", "redis") is False


def test_reset():
    g = _g()
    g.reset()
    assert g.stats()["nodes"] == 0 and g.nodes() == []


# ── thread safety ─────────────────────────────────────────────────────────────


def test_concurrent_writes_consistent():
    g = KnowledgeGraph()
    g.add_node("hub", "hub")
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            for i in range(100):
                nid = f"n{base}_{i}"
                g.add_node(nid, "leaf")
                g.add_edge("hub", "owns", nid)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert g.stats()["nodes"] == 1 + 6 * 100
    assert g.degree("hub")["out"] == 6 * 100
