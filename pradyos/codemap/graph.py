"""CODEMAP — the agent's structural self-knowledge.

So the machine can reason about (and eventually safely modify) its own code, it
needs a model of that code. CODEMAP parses Python source with the standard
library :mod:`ast` and builds a deterministic map of modules → the symbols they
define (functions, classes, methods) and the modules they depend on.

It answers the questions self-improvement and self-healing need:

  * ``module(name)``        — what does this module define and import?
  * ``defines(symbol)``     — where is this function/class defined?
  * ``dependencies(name)``  — what does this module import?
  * ``importers(target)``   — what would break if I change ``target``?
  * ``symbols(kind=...)``   — every function/class in the analysed code.

Pure and deterministic (``ast`` parsing only, no execution, no I/O), so it slots
into the constellation like every other plane and is tested against
hand-computed ground truth. It analyses *source text the caller supplies* — it
never imports or runs the code it maps.
"""

from __future__ import annotations

import ast
import threading
from dataclasses import dataclass, field
from typing import Any


class CodeMapError(RuntimeError):
    """Base class for CODEMAP failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _first_doc_line(node: ast.AST) -> str:
    doc = (
        ast.get_docstring(node, clean=True)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        else None
    )
    return doc.splitlines()[0].strip() if doc else ""


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    a = node.args
    names: list[str] = []
    names.extend(arg.arg for arg in a.posonlyargs)
    if a.posonlyargs:
        names.append("/")
    names.extend(arg.arg for arg in a.args)
    if a.vararg:
        names.append(f"*{a.vararg.arg}")
    elif a.kwonlyargs:
        names.append("*")
    names.extend(arg.arg for arg in a.kwonlyargs)
    if a.kwarg:
        names.append(f"**{a.kwarg.arg}")
    return f"{node.name}({', '.join(names)})"


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str  # function | class | method
    module: str
    lineno: int
    signature: str = ""
    doc: str = ""
    parent: str = ""  # owning class for methods

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "module": self.module,
            "lineno": self.lineno,
            "signature": self.signature,
            "doc": self.doc,
            "parent": self.parent,
        }


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    functions: tuple[Symbol, ...]
    classes: tuple[Symbol, ...]
    methods: tuple[Symbol, ...]
    imports: tuple[dict[str, Any], ...]
    dependencies: tuple[str, ...]
    loc: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "functions": [s.to_dict() for s in self.functions],
            "classes": [s.to_dict() for s in self.classes],
            "methods": [s.to_dict() for s in self.methods],
            "imports": [dict(i) for i in self.imports],
            "dependencies": list(self.dependencies),
            "loc": self.loc,
            "counts": {
                "functions": len(self.functions),
                "classes": len(self.classes),
                "methods": len(self.methods),
            },
        }


@dataclass
class _Parsed:
    info: ModuleInfo
    symbols: list[Symbol] = field(default_factory=list)


class CodeMap:
    """A deterministic structural map of analysed Python source."""

    def __init__(self) -> None:
        self._modules: dict[str, _Parsed] = {}
        self._lock = threading.RLock()

    # ── analysis ─────────────────────────────────────────────────────────────

    def analyze(self, module: str, source: str) -> dict[str, Any]:
        """Parse ``source`` as module ``module`` and store its structure."""
        if not _is_str(module):
            raise CodeMapError("module must be a non-empty string")
        if not isinstance(source, str):
            raise CodeMapError("source must be a string")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise CodeMapError(f"cannot parse {module!r}: {exc}") from exc

        functions: list[Symbol] = []
        classes: list[Symbol] = []
        methods: list[Symbol] = []
        imports: list[dict[str, Any]] = []
        deps: set[str] = set()

        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                functions.append(
                    Symbol(
                        node.name,
                        "function",
                        module,
                        node.lineno,
                        _signature(node),
                        _first_doc_line(node),
                    )
                )
            elif isinstance(node, ast.ClassDef):
                classes.append(
                    Symbol(node.name, "class", module, node.lineno, "", _first_doc_line(node))
                )
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                        methods.append(
                            Symbol(
                                sub.name,
                                "method",
                                module,
                                sub.lineno,
                                _signature(sub),
                                _first_doc_line(sub),
                                parent=node.name,
                            )
                        )
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
                imports.append({"kind": "import", "module": "", "names": names})
                deps.update(names)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = [a.name for a in node.names]
                imports.append({"kind": "from", "module": mod, "names": names, "level": node.level})
                if mod:
                    deps.add(mod)

        info = ModuleInfo(
            name=module,
            functions=tuple(functions),
            classes=tuple(classes),
            methods=tuple(methods),
            imports=tuple(imports),
            dependencies=tuple(sorted(deps)),
            loc=source.count("\n") + (1 if source and not source.endswith("\n") else 0),
        )
        with self._lock:
            self._modules[module] = _Parsed(info=info, symbols=[*functions, *classes, *methods])
        return info.to_dict()

    # ── queries ──────────────────────────────────────────────────────────────

    def module(self, name: str) -> dict[str, Any]:
        with self._lock:
            p = self._modules.get(name)
            if p is None:
                raise CodeMapError(f"unknown module {name!r}")
            return p.info.to_dict()

    def modules(self) -> list[str]:
        with self._lock:
            return sorted(self._modules)

    def defines(self, symbol: str) -> list[dict[str, Any]]:
        """Locate every function/class (top-level) defining ``symbol``."""
        if not _is_str(symbol):
            raise CodeMapError("symbol must be a non-empty string")
        with self._lock:
            out = [
                s.to_dict()
                for p in self._modules.values()
                for s in p.symbols
                if s.name == symbol and s.kind in ("function", "class")
            ]
        return sorted(out, key=lambda d: (d["module"], d["lineno"]))

    def dependencies(self, name: str) -> list[str]:
        with self._lock:
            p = self._modules.get(name)
            if p is None:
                raise CodeMapError(f"unknown module {name!r}")
            return list(p.info.dependencies)

    def importers(self, target: str) -> list[str]:
        """Which analysed modules import ``target`` (exact dependency match)."""
        if not _is_str(target):
            raise CodeMapError("target must be a non-empty string")
        with self._lock:
            return sorted(
                name for name, p in self._modules.items() if target in p.info.dependencies
            )

    def symbols(self, kind: str | None = None) -> list[dict[str, Any]]:
        if kind is not None and kind not in ("function", "class", "method"):
            raise CodeMapError("kind must be one of function|class|method")
        with self._lock:
            out = [
                s.to_dict()
                for p in self._modules.values()
                for s in p.symbols
                if kind is None or s.kind == kind
            ]
        return sorted(out, key=lambda d: (d["module"], d["lineno"], d["name"]))

    # ── introspection ────────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        with self._lock:
            mods = self._modules.values()
            return {
                "modules": len(self._modules),
                "functions": sum(len(p.info.functions) for p in mods),
                "classes": sum(len(p.info.classes) for p in mods),
                "methods": sum(len(p.info.methods) for p in mods),
                "imports": sum(len(p.info.imports) for p in mods),
            }

    def reset(self) -> None:
        with self._lock:
            self._modules.clear()
