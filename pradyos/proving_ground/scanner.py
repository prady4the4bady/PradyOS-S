"""Constitutional source scanner for the Proving Ground.

Scans Python source files in a cloned repository for patterns that would
violate the PRADY OS constitutional rules:

    - Direct os.system / subprocess calls without going through TITAN OPS
    - Hard-coded credential patterns (tokens, passwords, private keys)
    - Attempts to write outside the sandbox workspace
    - Imports of network libraries without ORACLE routing
    - Privileged syscalls (setuid, raw socket creation, etc.)

Severity levels:
    HARD_VIOLATION  — automatic REJECTED verdict (constitutional breach)
    SOFT_VIOLATION  — automatic QUARANTINED verdict (suspicious pattern)
    WARNING         — advisory; does not block admission alone
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from pradyos.proving_ground.verdict import ConstitutionScan

# ---------------------------------------------------------------------------
# Pattern catalogue
# ---------------------------------------------------------------------------

# Regex patterns → (severity, label)
_REGEX_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # Hard violations
    (re.compile(r"\bos\.system\s*\(", re.I), "HARD", "os.system() bypasses TITAN OPS"),
    (
        re.compile(r"\bsubprocess\.(call|run|Popen|check_output|check_call)\s*\(", re.I),
        "HARD",
        "raw subprocess call bypasses TITAN OPS",
    ),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "HARD", "private key literal"),
    (
        re.compile(r"(?i)(password|passwd|secret|token)\s*=\s*['\"][^'\"]{6,}['\"]"),
        "SOFT",
        "hard-coded credential literal",
    ),
    # Soft violations
    (re.compile(r"\beval\s*\("), "SOFT", "eval() call detected"),
    (re.compile(r"\bexec\s*\("), "SOFT", "exec() call detected"),
    (re.compile(r"__import__\s*\("), "SOFT", "__import__() dynamic import"),
    (re.compile(r"\bsetuid\s*\(|\bseteuid\s*\("), "SOFT", "setuid syscall attempt"),
    (re.compile(r"socket\.AF_PACKET|socket\.SOCK_RAW"), "SOFT", "raw socket creation"),
    # Warnings
    (re.compile(r"\bpickle\.loads?\s*\("), "WARN", "pickle deserialization (unsafe input risk)"),
    (re.compile(r"\byaml\.load\s*\((?!.*Loader)"), "WARN", "unsafe yaml.load() without Loader"),
    (re.compile(r"# noqa.*S\d{3}", re.I), "WARN", "bandit suppression annotation"),
]

# AST-based: dangerous top-level imports
_BLOCKED_IMPORTS: set[str] = {
    "ctypes",
    "cffi",  # native FFI — can bypass anything
    "winreg",
    "wincon",  # Windows registry direct writes
    "resource",  # POSIX resource limits manipulation
}

_WARN_IMPORTS: set[str] = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "paramiko",
    "fabric",  # SSH libraries
    "docker",  # Docker SDK direct
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def scan_directory(workspace: str, max_files: int = 500) -> ConstitutionScan:
    """Walk ``workspace`` and scan every .py file for constitutional patterns.

    Returns a :class:`ConstitutionScan` with violations and warnings populated.
    Files that cannot be parsed as valid Python are recorded as warnings.
    """
    result = ConstitutionScan()
    root = Path(workspace)

    py_files = sorted(root.rglob("*.py"))[:max_files]
    result.scanned_files = len(py_files)

    for fpath in py_files:
        rel = str(fpath.relative_to(root))
        try:
            source = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            result.warnings.append({"file": rel, "label": f"read error: {e}", "severity": "WARN"})
            continue

        # Regex scan
        for line_no, line in enumerate(source.splitlines(), 1):
            for pattern, sev, label in _REGEX_PATTERNS:
                if pattern.search(line):
                    entry: dict[str, Any] = {
                        "file": rel,
                        "line": line_no,
                        "label": label,
                        "severity": sev,
                        "excerpt": line.strip()[:120],
                    }
                    if sev == "HARD":
                        result.violations.append(entry)
                    elif sev == "SOFT":
                        result.violations.append(entry)
                    else:
                        result.warnings.append(entry)

        # AST scan
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError as e:
            result.warnings.append(
                {
                    "file": rel,
                    "label": f"syntax error: {e}",
                    "severity": "WARN",
                    "line": e.lineno,
                }
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [alias.name for alias in node.names]
                )
                for name in names:
                    top = name.split(".")[0]
                    if top in _BLOCKED_IMPORTS:
                        result.violations.append(
                            {
                                "file": rel,
                                "line": node.lineno,
                                "label": f"blocked import: {top!r}",
                                "severity": "SOFT",
                            }
                        )
                    elif top in _WARN_IMPORTS:
                        result.warnings.append(
                            {
                                "file": rel,
                                "line": node.lineno,
                                "label": f"network import without ORACLE routing: {top!r}",
                                "severity": "WARN",
                            }
                        )

    return result


def scan_dependencies(workspace: str) -> tuple[str, int, list[dict[str, Any]]]:
    """Return (manager, total_count, flagged_packages) for the repo's deps.

    Supported manifests: requirements.txt, pyproject.toml [project.dependencies],
    setup.cfg [options.install_requires], package.json.
    """
    root = Path(workspace)
    flagged: list[dict[str, Any]] = []
    total = 0
    manager = "unknown"

    # --- Python: requirements.txt ---
    req_file = root / "requirements.txt"
    if req_file.exists():
        manager = "pip"
        lines = [
            l.strip()
            for l in req_file.read_text(errors="replace").splitlines()
            if l.strip() and not l.startswith("#")
        ]
        total = len(lines)
        for line in lines:
            pkg = re.split(r"[>=<!;@\[]", line)[0].strip().lower()
            if pkg in _SUSPICIOUS_PACKAGES:
                flagged.append({"package": pkg, "reason": _SUSPICIOUS_PACKAGES[pkg]})
        return manager, total, flagged

    # --- Python: pyproject.toml ---
    ppt = root / "pyproject.toml"
    if ppt.exists():
        manager = "pip"
        text = ppt.read_text(errors="replace")
        # Crude extraction — full TOML parse would add a dep
        in_deps = False
        for line in text.splitlines():
            ls = line.strip()
            if ls.startswith("dependencies"):
                in_deps = True
                continue
            if in_deps:
                if ls.startswith("["):
                    break
                if ls.startswith('"') or ls.startswith("'"):
                    dep = re.split(r"[>=<!;@\[\s\"']", ls.strip("\"',[] "))[0].lower()
                    if dep:
                        total += 1
                        if dep in _SUSPICIOUS_PACKAGES:
                            flagged.append({"package": dep, "reason": _SUSPICIOUS_PACKAGES[dep]})

    # --- Node: package.json ---
    pkgjson = root / "package.json"
    if pkgjson.exists():
        manager = "npm"
        import json

        try:
            data = json.loads(pkgjson.read_text(errors="replace"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            total = len(deps)
            for pkg in deps:
                if pkg.lower() in _SUSPICIOUS_PACKAGES:
                    flagged.append({"package": pkg, "reason": _SUSPICIOUS_PACKAGES[pkg.lower()]})
        except Exception:  # noqa: BLE001
            pass

    return manager, total, flagged


# Packages known to be risky or supply-chain targets
_SUSPICIOUS_PACKAGES: dict[str, str] = {
    "colourama": "typosquatting target (colourама/colorama)",
    "python-openssl": "shadow package for pyOpenSSL",
    "setup-tools": "typosquatting setuptools",
    "python-utils": "historically used in supply-chain attacks",
    "urllib4": "not a real package — urllib3 typosquat",
    "request": "urllib3/requests typosquat",
    "event-stream": "historic npm supply-chain attack",
    "flatmap-stream": "historic npm supply-chain sub-attack",
}
