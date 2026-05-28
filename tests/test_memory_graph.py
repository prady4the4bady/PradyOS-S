"""Phase 47C — 20 tests for pradyos.core.memory_graph.MemoryGraph."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.memory_graph import GraphEdge, GraphNode, MemoryGraph
from pradyos.core.snapshot_store import SnapshotStore


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty():
    g = MemoryGraph()
    assert g.node_count() == 0
    assert g.edge_count() == 0


# ── add_node ──────────────────────────────────────────────────────────────────

def test_add_node_returns_graphnode():
    g = MemoryGraph()
    node = g.add_node("alpha")
    assert isinstance(node, GraphNode)
    assert node.name == "alpha"


def test_add_node_increments_count():
    g = MemoryGraph()
    g.add_node("a")
    g.add_node("b")
    assert g.node_count() == 2


def test_add_node_duplicate_updates_metadata():
    g = MemoryGraph()
    g.add_node("a", metadata={"v": 1})
    g.add_node("a", metadata={"v": 2})
    assert g.node_count() == 1
    assert g.get_node("a").metadata == {"v": 2}


# ── add_edge ──────────────────────────────────────────────────────────────────

def test_add_edge_returns_graphedge():
    g = MemoryGraph()
    e = g.add_edge("a", "b", "knows")
    assert isinstance(e, GraphEdge)
    assert e.src == "a"
    assert e.dst == "b"


def test_add_edge_increments_count():
    g = MemoryGraph()
    g.add_edge("a", "b", "knows")
    assert g.edge_count() == 1


def test_add_edge_auto_creates_src():
    g = MemoryGraph()
    g.add_edge("newsrc", "b", "knows")
    assert g.get_node("newsrc") is not None


def test_add_edge_auto_creates_dst():
    g = MemoryGraph()
    g.add_edge("a", "newdst", "knows")
    assert g.get_node("newdst") is not None


def test_add_edge_duplicate_updates_weight():
    g = MemoryGraph()
    g.add_edge("a", "b", "knows", weight=1.0)
    g.add_edge("a", "b", "knows", weight=5.0)
    assert g.edge_count() == 1
    edge = g._edges[0]
    assert edge.weight == 5.0


# ── get_node ──────────────────────────────────────────────────────────────────

def test_get_node_returns_correct():
    g = MemoryGraph()
    g.add_node("alpha", metadata={"role": "primary"})
    node = g.get_node("alpha")
    assert node is not None
    assert node.metadata == {"role": "primary"}


def test_get_node_returns_none_unknown():
    g = MemoryGraph()
    assert g.get_node("missing") is None


# ── neighbors ─────────────────────────────────────────────────────────────────

def test_get_neighbors_returns_connected():
    g = MemoryGraph()
    g.add_edge("a", "b", "knows")
    g.add_edge("a", "c", "follows")
    names = sorted(n.name for n in g.get_neighbors("a"))
    assert names == ["b", "c"]


def test_get_neighbors_filters_by_relation():
    g = MemoryGraph()
    g.add_edge("a", "b", "knows")
    g.add_edge("a", "c", "follows")
    names = [n.name for n in g.get_neighbors("a", relation="knows")]
    assert names == ["b"]


def test_get_neighbors_unknown_returns_empty():
    g = MemoryGraph()
    assert g.get_neighbors("phantom") == []


# ── shortest_path ─────────────────────────────────────────────────────────────

def test_shortest_path_src_equals_dst():
    g = MemoryGraph()
    g.add_node("a")
    assert g.shortest_path("a", "a") == ["a"]


def test_shortest_path_simple_chain():
    g = MemoryGraph()
    g.add_edge("a", "b", "x")
    g.add_edge("b", "c", "x")
    assert g.shortest_path("a", "c") == ["a", "b", "c"]


def test_shortest_path_no_path_returns_none():
    g = MemoryGraph()
    g.add_node("a")
    g.add_node("b")
    assert g.shortest_path("a", "b") is None


def test_shortest_path_unknown_src_returns_none():
    g = MemoryGraph()
    g.add_node("b")
    assert g.shortest_path("phantom", "b") is None


# ── persistence ───────────────────────────────────────────────────────────────

def test_persistence_save_and_reload(tmp_path):
    store = SnapshotStore(base_dir=tmp_path)
    g1 = MemoryGraph(snapshot_store=store)
    g1.add_node("alpha", metadata={"x": 1})
    g1.add_edge("alpha", "beta", "knows", weight=2.5)

    g2 = MemoryGraph(snapshot_store=store)
    assert g2.node_count() == 2  # alpha + beta (auto-created)
    assert g2.edge_count() == 1
    alpha = g2.get_node("alpha")
    assert alpha is not None
    assert alpha.metadata == {"x": 1}
    assert g2._edges[0].weight == 2.5


# ── thread safety ────────────────────────────────────────────────────────────

def test_thread_safety_concurrent_add_node():
    g = MemoryGraph()
    errors: list[Exception] = []

    def worker(i: int):
        try:
            g.add_node(f"n{i}", metadata={"idx": i})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert g.node_count() == 30
