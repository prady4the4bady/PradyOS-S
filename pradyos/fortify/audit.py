"""FORTIFY — self-hardening audit of the agent's own code.

So the machine can heal and harden itself, it needs to find its *own* fragility.
FORTIFY scans Python source for reliability/robustness weaknesses and returns a
prioritised hardening report. It is **distinct from
``pradyos.proving_ground.scanner``** — that scanner enforces the *constitution*
(os.system, credentials, privileged syscalls); FORTIFY is about *robustness*
(swallowed errors, missing exit conditions, shared mutable state, debt markers).

Rules (deterministic, AST + regex, parses-not-executes):

  * ``bare_except``      HIGH   — ``except:`` swallows SystemExit/KeyboardInterrupt
  * ``swallowed_error``  MEDIUM — ``except ...:`` whose body is only pass/...
  * ``mutable_default``  HIGH   — a function default of ``[]``/``{}``/``set()``
  * ``assert_validation``MEDIUM — ``assert`` used for validation (stripped under -O)
  * ``infinite_loop``    LOW    — ``while True:`` with no break/return/raise
  * ``debt_marker``      LOW    — TODO / FIXME / XXX / HACK comments

Each finding carries a line, severity, message, and a remediation hint. The
report's ``risk`` is a weighted sum (HIGH 3 / MEDIUM 2 / LOW 1). Composes with
CODEMAP (structure), the REVIEW GATE (gate the fixes) and SKILLS (remember them).
"""

from __future__ import annotations

import ast
import re
import threading
from dataclasses import dataclass
from typing import Any

_SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
_DEBT = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")

# The rule catalogue (id → severity + remediation), surfaced via the API.
RULES: dict[str, dict[str, str]] = {
    "bare_except": {
        "severity": "high",
        "remediation": "catch specific exceptions, not a bare except",
    },
    "swallowed_error": {
        "severity": "medium",
        "remediation": "log or handle the exception instead of silently passing",
    },
    "mutable_default": {
        "severity": "high",
        "remediation": "default to None and create the mutable inside the function",
    },
    "assert_validation": {
        "severity": "medium",
        "remediation": "raise an explicit error; assert is stripped under python -O",
    },
    "infinite_loop": {
        "severity": "low",
        "remediation": "ensure the loop has a reachable break/return/raise",
    },
    "debt_marker": {
        "severity": "low",
        "remediation": "resolve or track the TODO/FIXME",
    },
}


class FortifyError(RuntimeError):
    """Base class for FORTIFY failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    line: int
    message: str
    remediation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "line": self.line,
            "message": self.message,
            "remediation": self.remediation,
        }


def _mk(rule: str, line: int, message: str) -> Finding:
    meta = RULES[rule]
    return Finding(rule, meta["severity"], line, message, meta["remediation"])


def _body_has_exit(body: list[ast.stmt]) -> bool:
    for node in body:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Break | ast.Return | ast.Raise):
                return True
    return False


def _is_mutable_default(node: ast.expr) -> bool:
    if isinstance(node, ast.List | ast.Dict | ast.Set):
        return True
    return bool(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("list", "dict", "set")
        and not node.args
        and not node.keywords
    )


class FortifyEngine:
    """Scans source for robustness weaknesses and stores hardening reports."""

    def __init__(self) -> None:
        self._reports: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    # ── audit ────────────────────────────────────────────────────────────────

    def audit(self, module: str, source: str) -> dict[str, Any]:
        """Scan ``source`` for weaknesses; store and return the report."""
        if not _is_str(module):
            raise FortifyError("module must be a non-empty string")
        if not isinstance(source, str):
            raise FortifyError("source must be a string")

        findings: list[Finding] = []
        try:
            tree: ast.AST | None = ast.parse(source)
        except SyntaxError as exc:
            tree = None
            findings.append(
                Finding(
                    "parse_error",
                    "high",
                    exc.lineno or 1,
                    f"source does not parse: {exc.msg}",
                    "fix the syntax error before hardening",
                )
            )

        if tree is not None:
            findings.extend(self._ast_findings(tree))
        findings.extend(self._regex_findings(source))

        findings.sort(key=lambda f: (_SEVERITY_RANK.get(f.severity, 9), f.line, f.rule))
        by_severity: dict[str, int] = {}
        risk = 0
        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            risk += _SEVERITY_WEIGHT.get(f.severity, 1)

        report = {
            "module": module,
            "findings": [f.to_dict() for f in findings],
            "by_severity": by_severity,
            "risk": risk,
            "finding_count": len(findings),
        }
        with self._lock:
            self._reports[module] = report
        return report

    def _ast_findings(self, tree: ast.AST) -> list[Finding]:
        out: list[Finding] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    out.append(_mk("bare_except", node.lineno, "bare 'except:' catches everything"))
                elif self._is_broad(node.type) and self._only_pass(node.body):
                    out.append(
                        _mk("swallowed_error", node.lineno, "exception caught and silently ignored")
                    )
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                defaults = [d for d in node.args.defaults if d is not None]
                defaults += [d for d in node.args.kw_defaults if d is not None]
                if any(_is_mutable_default(d) for d in defaults):
                    out.append(
                        _mk(
                            "mutable_default",
                            node.lineno,
                            f"'{node.name}' has a mutable default arg",
                        )
                    )
            elif isinstance(node, ast.Assert):
                out.append(_mk("assert_validation", node.lineno, "assert used for validation"))
            elif isinstance(node, ast.While) and self._is_true(node.test):
                if not _body_has_exit(node.body):
                    out.append(_mk("infinite_loop", node.lineno, "'while True' with no exit path"))
        return out

    @staticmethod
    def _is_broad(exc_type: ast.expr) -> bool:
        return isinstance(exc_type, ast.Name) and exc_type.id in ("Exception", "BaseException")

    @staticmethod
    def _only_pass(body: list[ast.stmt]) -> bool:
        if len(body) != 1:
            return False
        stmt = body[0]
        if isinstance(stmt, ast.Pass):
            return True
        return bool(
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis
        )

    @staticmethod
    def _is_true(test: ast.expr) -> bool:
        return isinstance(test, ast.Constant) and test.value is True

    @staticmethod
    def _regex_findings(source: str) -> list[Finding]:
        out: list[Finding] = []
        for i, line in enumerate(source.splitlines(), start=1):
            if _DEBT.search(line):
                marker = _DEBT.search(line).group(1)  # type: ignore[union-attr]
                out.append(_mk("debt_marker", i, f"{marker} marker — tracked tech debt"))
        return out

    # ── introspection ────────────────────────────────────────────────────────

    def report(self, module: str) -> dict[str, Any]:
        with self._lock:
            r = self._reports.get(module)
            if r is None:
                raise FortifyError(f"unknown module {module!r}")
            return dict(r)

    def reports(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._reports.values()]

    def rules(self) -> dict[str, dict[str, str]]:
        return {k: dict(v) for k, v in RULES.items()}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total_risk = sum(r["risk"] for r in self._reports.values())
            total_findings = sum(r["finding_count"] for r in self._reports.values())
            return {
                "modules": len(self._reports),
                "total_findings": total_findings,
                "total_risk": total_risk,
            }

    def reset(self) -> None:
        with self._lock:
            self._reports.clear()
