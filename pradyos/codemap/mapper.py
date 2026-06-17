"""Mapper — filesystem walk + CodeMap to produce a JSON module index.

Scans the ``pradyos/`` package tree, feeds each ``.py`` file through
:class:`~pradyos.codemap.graph.CodeMap`, and collects the results into a
structured index (dict of module path → symbols/imports).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pradyos.codemap.graph import CodeMap

_CODEMAP_DIR = Path(__file__).resolve().parent.parent.parent
_PACKAGE = _CODEMAP_DIR / "pradyos"


def scan_package(root: str | Path = _PACKAGE) -> dict[str, Any]:
    """Walk ``root`` for ``.py`` files, parse each with ``CodeMap``, return index."""
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    index: dict[str, Any] = {}
    cm = CodeMap()

    for pyfile in sorted(root.rglob("*.py")):
        if "__pycache__" in pyfile.parts:
            continue
        rel = pyfile.relative_to(root).with_suffix("").as_posix().replace("/", ".")
        try:
            source = pyfile.read_text(encoding="utf-8")
            info = cm.analyze(rel, source)
            index[str(pyfile.relative_to(_CODEMAP_DIR).as_posix())] = {
                "functions": [s["name"] for s in info.get("functions", [])],
                "classes": [s["name"] for s in info.get("classes", [])],
                "methods": [s["name"] for s in info.get("methods", [])],
                "dependencies": list(info.get("dependencies", [])),
                "loc": info.get("loc", 0),
            }
        except Exception as exc:
            index[str(pyfile.relative_to(_CODEMAP_DIR).as_posix())] = {"error": str(exc)}

    return {"root": str(root), "modules": index, "total_modules": len(index)}


def export_json(root: str | Path = _PACKAGE, output: str | None = None) -> str:
    """Scan and return (or write) a JSON module index."""
    data = scan_package(root)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if output:
        Path(output).write_text(text, encoding="utf-8")
    return text
