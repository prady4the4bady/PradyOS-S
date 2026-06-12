"""CODEMAP tests — AST structural extraction verified against known source."""

from __future__ import annotations

import pytest

from pradyos.codemap import CodeMap, CodeMapError

SAMPLE = '''\
"""My module."""
import os
from pradyos.core.bus import EventBus, get_bus


def alpha(x, y=1):
    """Alpha does things."""
    return x + y


async def beta(*args, **kwargs):
    return None


class Widget:
    """A widget."""

    def __init__(self, name):
        self.name = name

    def render(self):
        return self.name
'''


def _cm() -> CodeMap:
    cm = CodeMap()
    cm.analyze("demo.mod", SAMPLE)
    return cm


# ── analysis ──────────────────────────────────────────────────────────────────


def test_analyze_counts():
    summary = CodeMap().analyze("demo.mod", SAMPLE)
    assert summary["counts"] == {"functions": 2, "classes": 1, "methods": 2}
    assert summary["dependencies"] == ["os", "pradyos.core.bus"]


def test_module_structure_and_signatures():
    m = _cm().module("demo.mod")
    assert [f["name"] for f in m["functions"]] == ["alpha", "beta"]
    sigs = {f["name"]: f["signature"] for f in m["functions"]}
    assert sigs["alpha"] == "alpha(x, y)" and sigs["beta"] == "beta(*args, **kwargs)"
    assert m["functions"][0]["doc"] == "Alpha does things."
    assert [c["name"] for c in m["classes"]] == ["Widget"]
    assert {mt["name"] for mt in m["methods"]} == {"__init__", "render"}
    assert m["methods"][0]["parent"] == "Widget"


def test_analyze_syntax_error_raises():
    with pytest.raises(CodeMapError):
        CodeMap().analyze("bad", "def (:\n")


def test_analyze_validation():
    cm = CodeMap()
    with pytest.raises(CodeMapError):
        cm.analyze("", "x = 1")
    with pytest.raises(CodeMapError):
        cm.analyze("m", 123)  # source not a string


# ── queries ───────────────────────────────────────────────────────────────────


def test_defines_locates_symbols():
    cm = _cm()
    d = cm.defines("alpha")
    assert len(d) == 1 and d[0]["module"] == "demo.mod" and d[0]["kind"] == "function"
    assert cm.defines("Widget")[0]["kind"] == "class"
    assert cm.defines("render") == []  # methods are not top-level definitions
    assert cm.defines("nonexistent") == []


def test_dependencies_and_importers():
    cm = CodeMap()
    cm.analyze("app.main", "from app.util import helper\nimport os\n")
    cm.analyze("app.util", "def helper():\n    pass\n")
    assert cm.dependencies("app.main") == ["app.util", "os"]
    assert cm.importers("app.util") == ["app.main"]
    assert cm.importers("os") == ["app.main"]
    assert cm.importers("unused.module") == []


def test_symbols_by_kind():
    cm = _cm()
    assert [s["name"] for s in cm.symbols(kind="function")] == ["alpha", "beta"]
    assert [s["name"] for s in cm.symbols(kind="class")] == ["Widget"]
    assert {s["name"] for s in cm.symbols(kind="method")} == {"__init__", "render"}
    assert len(cm.symbols()) == 5  # 2 functions + 1 class + 2 methods


def test_query_validation():
    cm = _cm()
    with pytest.raises(CodeMapError):
        cm.module("ghost")
    with pytest.raises(CodeMapError):
        cm.dependencies("ghost")
    with pytest.raises(CodeMapError):
        cm.symbols(kind="variable")
    with pytest.raises(CodeMapError):
        cm.defines("")


# ── modules / summary / reset ─────────────────────────────────────────────────


def test_modules_listed_sorted():
    cm = CodeMap()
    cm.analyze("b.mod", "x = 1")
    cm.analyze("a.mod", "y = 2")
    assert cm.modules() == ["a.mod", "b.mod"]


def test_summary_and_reset():
    cm = _cm()
    s = cm.summary()
    assert s == {"modules": 1, "functions": 2, "classes": 1, "methods": 2, "imports": 2}
    cm.reset()
    assert cm.summary()["modules"] == 0
