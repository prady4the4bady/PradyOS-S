"""Proving Ground CI Guard (Phase 4D).

Before ``CampaignEngine`` dispatches any step to TITAN, this guard scans
the step's command string through a lightweight static analyser.

Verdicts
--------
``Verdict.CLEAN``   — no issues detected; proceed normally
``Verdict.WARN``    — suspicious pattern; log a warning and proceed
``Verdict.BLOCKED`` — critical violation; do NOT dispatch to TITAN

Integration hook
----------------
Call ``CampaignCIGuard.check(instruction)`` before dispatching a
``TitanInstruction``. The guard returns a ``Verdict`` + reason string::

    guard = CampaignCIGuard()
    verdict, reason = guard.check(instruction)
    if verdict == Verdict.BLOCKED:
        # mark node FAILED, emit campaign.blocked event
        ...
    elif verdict == Verdict.WARN:
        log.warning("CI WARN: %s", reason)
        # proceed with dispatch
    else:
        # proceed normally

The guard is fully synchronous so it can be called from both sync and
async contexts.

Windows safety
--------------
* All paths via pathlib.Path
* No AF_UNIX, no fork(), no os.killpg()
* No uvloop dependency
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any

log = logging.getLogger("pradyos.proving_ground_ci")


# ---------------------------------------------------------------------------
# Verdict enum
# ---------------------------------------------------------------------------


class Verdict(str, Enum):
    CLEAN = "CLEAN"
    WARN = "WARN"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Pattern tables
# ---------------------------------------------------------------------------

# Patterns that BLOCK immediately — critical/destructive commands
_BLOCKED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+-rf\s+/(?:\s|$)"), "rm -rf / is destructive"),
    (re.compile(r"\bdd\s+if=.*of=/dev/(s|h|v|xv)d[a-z]"), "dd to raw device"),
    (re.compile(r"\bmkfs\b"), "filesystem format command"),
    (re.compile(r"\bformat\s+[a-zA-Z]:\\"), "Windows format command"),
    (re.compile(r"\b(shutdown|reboot|halt|poweroff)\b.*(-[fFhHrRpP]|\s|$)"), "system shutdown/reboot"),
    (re.compile(r">\s*/dev/s[a-z]+"), "redirect to raw block device"),
    (re.compile(r"\bdel\s+/[sS]\s+/[qQ]?\s+[a-zA-Z]:\\"), "Windows recursive delete"),
    (re.compile(r"\brdisk\b"), "raw disk access"),
    (re.compile(r"\bkill\s+-9\s+1\b"), "kill init/PID 1"),
    (re.compile(r"__import__\s*\(\s*['\"]os['\"]\s*\).*system"), "python os.system injection"),
    (re.compile(r"\bcurl\b.*\|\s*(ba)?sh\b"), "curl-pipe-to-shell (RCE risk)"),
    (re.compile(r"\bwget\b.*-O\s*-.*\|\s*(ba)?sh\b"), "wget-pipe-to-shell (RCE risk)"),
]

# Patterns that WARN but do not block
_WARN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsudo\b"), "sudo usage"),
    (re.compile(r"\bchmod\s+777\b"), "chmod 777 — broad permissions"),
    (re.compile(r"\bchown\s+root\b"), "chown to root"),
    (re.compile(r"\bapt(-get)?\s+install\b"), "package installation"),
    (re.compile(r"\bpip\s+install\b"), "pip install"),
    (re.compile(r"\bnpm\s+install\b"), "npm install"),
    (re.compile(r"\bcurl\b.*http://"), "plain HTTP (not HTTPS)"),
    (re.compile(r"\bwget\b.*http://"), "plain HTTP (not HTTPS)"),
    (re.compile(r"\beval\b\s*\("), "eval() usage"),
    (re.compile(r"\bdropdb\b|\bdropdatabase\b", re.IGNORECASE), "database drop"),
    (re.compile(r"\btruncate\b.*table\b", re.IGNORECASE), "table truncation"),
    (re.compile(r"\bnetsh\s+advfirewall\b", re.IGNORECASE), "Windows firewall modification"),
    (re.compile(r"\breg\s+(add|delete)\b", re.IGNORECASE), "Windows registry modification"),
]


# ---------------------------------------------------------------------------
# ProvingGroundPipeline — reusable scan surface
# ---------------------------------------------------------------------------


class ProvingGroundPipeline:
    """Lightweight static scanner that can be called from the CI guard.

    Unlike the full ``AdmissionPipeline`` (which clones repos and runs tests),
    this pipeline only performs static pattern analysis on a command string.
    """

    def scan(self, command: str) -> tuple[Verdict, str]:
        """Scan a command string and return (verdict, reason).

        This is the fast path used by the CI guard — no subprocess, no I/O.
        """
        if not command or not command.strip():
            return Verdict.CLEAN, ""

        # Normalise: collapse extra whitespace for pattern matching
        normalised = " ".join(command.split())

        for pattern, label in _BLOCKED_PATTERNS:
            if pattern.search(normalised):
                log.warning("CI BLOCKED: pattern=%s cmd=%r", label, normalised[:120])
                return Verdict.BLOCKED, f"blocked pattern: {label}"

        for pattern, label in _WARN_PATTERNS:
            if pattern.search(normalised):
                log.info("CI WARN: pattern=%s cmd=%r", label, normalised[:120])
                return Verdict.WARN, f"warning pattern: {label}"

        return Verdict.CLEAN, ""


# ---------------------------------------------------------------------------
# CampaignCIGuard
# ---------------------------------------------------------------------------


class CampaignCIGuard:
    """Pre-dispatch gate: checks TitanInstructions before they reach TITAN.

    Usage::

        guard = CampaignCIGuard()
        verdict, reason = guard.check(instruction)
    """

    def __init__(self, pipeline: ProvingGroundPipeline | None = None) -> None:
        self._pipeline = pipeline or ProvingGroundPipeline()

    def check(self, instruction: Any) -> tuple[Verdict, str]:
        """Scan *instruction* and return (Verdict, reason).

        Parameters
        ----------
        instruction:
            A ``TitanInstruction`` or any object with a ``command`` attribute.
            If neither is available, falls back to ``str(instruction)``.
        """
        command = _extract_command(instruction)
        verdict, reason = self._pipeline.scan(command)

        if verdict == Verdict.BLOCKED:
            log.error(
                "CampaignCIGuard BLOCKED instruction: %r — %s",
                command[:80],
                reason,
            )
        elif verdict == Verdict.WARN:
            log.warning(
                "CampaignCIGuard WARN instruction: %r — %s",
                command[:80],
                reason,
            )

        return verdict, reason


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_command(instruction: Any) -> str:
    """Extract a command string from a TitanInstruction or dict."""
    if instruction is None:
        return ""
    if isinstance(instruction, str):
        return instruction
    if isinstance(instruction, dict):
        return str(instruction.get("command") or instruction.get("intent") or "")
    # TitanInstruction object
    cmd = getattr(instruction, "command", None)
    if cmd:
        return str(cmd)
    intent = getattr(instruction, "intent", None)
    if intent:
        return str(intent)
    return str(instruction)
