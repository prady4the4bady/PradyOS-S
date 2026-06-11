"""Phase 70 — unit tests for pradyos.core.dependency_graph.DependencyGraph.

Edge convention throughout: ``add_dependency(a, b)`` means "a depends on b"
(edge a -> b). So ``get_dependencies(a) == [b]`` and ``get_dependents(b) == [a]``.
"""
from __future__ import annotations

import threading

import pytest

from pradyos.core.dependency_graph import DependencyGraph, CycleError


def _valid_cycle(graph: DependencyGraph, path: list[str]) -> bool:
    """True if ``path`` is a closed walk over real edges (frm -> to)."""
    if not path or len(path) < 2 or path[0] != path[-1]:
        return False
    for frm, to in zip(path, path[1:]):
        if to not in graph.get_dependencies(frm):
            return False
    return True


# ── construction / basic mutation ────────────────────────────────────────────

def test_init_empty():
    g = DependencyGraph()
    assert g.nodes() == []


def test_add_dependency_creates_both_nodes():
    g = DependencyGraph()
    g.add_dependency("web", "db")
    assert g.nodes() == ["db", "web"]


def test_get_dependencies():
    g = DependencyGraph()
    g.add_dependency("web", "db")
    g.add_dependency("web", "cache")
    assert g.get_dependencies("web") == ["cache", "db"]


def test_get_dependents():
    g = DependencyGraph()
    g.add_dependency("web", "db")
    g.add_dependency("api", "db")
    assert g.get_dependents("db") == ["api", "web"]


def test_add_is_idempotent():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("a", "b")
    assert g.get_dependencies("a") == ["b"]


def test_remove_dependency_returns_true():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    assert g.remove_dependency("a", "b") is True
    assert g.get_dependencies("a") == []
    assert g.get_dependents("b") == []


def test_remove_nonexistent_returns_false():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    assert g.remove_dependency("a", "zzz") is False
    assert g.remove_dependency("nope", "b") is False


def test_remove_keeps_nodes():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.remove_dependency("a", "b")
    assert g.has_node("a") and g.has_node("b")


# ── membership / unknown-node queries ────────────────────────────────────────

def test_has_node():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    assert g.has_node("a")
    assert not g.has_node("ghost")


def test_unknown_node_queries_are_empty():
    g = DependencyGraph()
    assert g.get_dependencies("ghost") == []
    assert g.get_dependents("ghost") == []
    assert g.impact_score("ghost") == 0


# ── topological sort ──────────────────────────────────────────────────────────

def test_topological_sort_linear_chain():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("b", "c")
    g.add_dependency("c", "d")
    # dependency-first: each node after everything it depends on
    assert g.topological_sort() == ["d", "c", "b", "a"]


def test_topological_sort_respects_every_edge():
    g = DependencyGraph()
    edges = [("web", "db"), ("web", "cache"), ("api", "db"), ("worker", "cache")]
    for frm, to in edges:
        g.add_dependency(frm, to)
    order = g.topological_sort()
    assert set(order) == {"web", "db", "cache", "api", "worker"}
    for frm, to in edges:
        assert order.index(to) < order.index(frm)


def test_topological_sort_is_deterministic():
    g = DependencyGraph()
    g.add_dependency("web", "db")
    g.add_dependency("api", "db")
    assert g.topological_sort() == g.topological_sort()


def test_topological_sort_from_node_scopes_to_closure():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("a", "c")
    g.add_dependency("b", "d")
    g.add_dependency("x", "y")  # unrelated component
    order = g.topological_sort("a")
    assert set(order) == {"a", "b", "c", "d"}
    assert "x" not in order and "y" not in order
    assert order.index("d") < order.index("b") < order.index("a")


def test_topological_sort_raises_on_cycle():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("b", "c")
    g.add_dependency("c", "a")
    with pytest.raises(CycleError):
        g.topological_sort()


def test_cycle_error_carries_valid_path():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("b", "c")
    g.add_dependency("c", "a")
    with pytest.raises(CycleError) as excinfo:
        g.topological_sort()
    assert _valid_cycle(g, excinfo.value.cycle)


# ── cycle detection ────────────────────────────────────────────────────────────

def test_find_cycle_none_when_acyclic():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("b", "c")
    assert g.find_cycle() is None


def test_find_cycle_detects_simple_cycle():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("b", "a")
    cycle = g.find_cycle()
    assert cycle is not None
    assert _valid_cycle(g, cycle)


def test_find_cycle_self_loop():
    g = DependencyGraph()
    g.add_dependency("a", "a")
    cycle = g.find_cycle()
    assert cycle == ["a", "a"]


# ── impact score ──────────────────────────────────────────────────────────────

def test_impact_score_direct_dependents():
    g = DependencyGraph()
    g.add_dependency("web", "db")
    g.add_dependency("api", "db")
    assert g.impact_score("db") == 2
    assert g.impact_score("web") == 0


def test_impact_score_transitive():
    g = DependencyGraph()
    g.add_dependency("a", "b")
    g.add_dependency("b", "c")
    g.add_dependency("c", "d")
    # everything (a, b, c) transitively depends on d
    assert g.impact_score("d") == 3
    assert g.impact_score("c") == 2
    assert g.impact_score("a") == 0


# ── describe snapshot ──────────────────────────────────────────────────────────

def test_describe_has_all_fields():
    g = DependencyGraph()
    g.add_dependency("web", "db")
    d = g.describe("db")
    assert set(d) == {"node", "exists", "dependencies", "dependents", "impact_score"}
    assert d["node"] == "db"
    assert d["exists"] is True
    assert d["dependents"] == ["web"]
    assert d["impact_score"] == 1


# ── thread safety ──────────────────────────────────────────────────────────────

def test_thread_safety_concurrent_add():
    g = DependencyGraph()
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            for _ in range(50):
                g.add_dependency("root", f"child{i}")
                g.add_dependency(f"child{i}", "leaf")
        except Exception as exc:  # pragma: no cover - only on a real race failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(g.get_dependencies("root")) == 20
    assert len(g.get_dependents("leaf")) == 20
    # leaf is depended on by 20 children plus, transitively, root -> 21
    assert g.impact_score("leaf") == 21
