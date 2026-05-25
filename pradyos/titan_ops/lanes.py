"""Subprocess lane configuration.

The two foundational lanes (blueprint §8.2):

    UNPRIVILEGED — default. No sudo. Runs as the daemon user.
    PRIVILEGED   — constitutional admin. Prepends sudo (or runs as root
                   if the daemon is already root). Recorded distinctly
                   in the audit log.

SANDBOX is the NIGHT CITADEL experiment lane (Phase 4) — wired in here
so the contract is stable now.
"""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass

from pradyos.core.types import ExecutionLane


@dataclass(slots=True)
class LaneConfig:
    name: ExecutionLane
    command_prefix: list[str]
    extra_env: dict[str, str]
    requires_root: bool

    def wrap(self, argv: list[str]) -> list[str]:
        if not self.command_prefix:
            return argv
        return [*self.command_prefix, *argv]


def _running_as_root() -> bool:
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except AttributeError:
        return False  # non-POSIX dev (Windows) — treat as non-root


def lane_for(lane: ExecutionLane) -> LaneConfig:
    """Return the lane configuration. Falls back gracefully on non-POSIX
    or non-sudo systems (used in tests / dev shells)."""
    if lane is ExecutionLane.PRIVILEGED:
        if _running_as_root():
            return LaneConfig(lane, [], {}, requires_root=True)
        # Non-interactive sudo only — interactive sudo would block the daemon.
        if _which("sudo"):
            return LaneConfig(lane, ["sudo", "-n"], {}, requires_root=True)
        # No path to root -> fall back to unprivileged but mark it.
        return LaneConfig(lane, [], {"PRADYOS_PRIVILEGE_DEGRADED": "1"}, requires_root=True)

    if lane is ExecutionLane.SANDBOX:
        # Phase 0 sandbox: no kernel-level isolation yet (Phase 4 wires nsjail
        # / bwrap / firejail per repo-admission verdict). Resource bounds via
        # env are enforced; the contract is stable.
        return LaneConfig(
            lane,
            [],
            {"PRADYOS_SANDBOX": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            requires_root=False,
        )

    return LaneConfig(ExecutionLane.UNPRIVILEGED, [], {}, requires_root=False)


def _which(name: str) -> str | None:
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(d, name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def parse_command(command: str) -> list[str]:
    """Safe argv split. Empty / whitespace strings raise.

    On Windows, shlex default POSIX mode treats backslashes as escape
    characters, which silently mangles Windows paths such as
    C:\\Users\\foo\\python.exe to CUsersfoo python.exe. We therefore
    use posix=False on Windows (backslashes are preserved) and then strip
    the surrounding quotes that posix=False leaves on each token.
    """
    if not command or not command.strip():
        raise ValueError("empty command")
    if sys.platform == "win32":
        tokens = shlex.split(command, posix=False)
        result: list[str] = []
        for tok in tokens:
            # posix=False keeps outer quote characters as part of the token;
            # strip one layer of matching surrounding quotes if present.
            if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ('"', "'"):
                tok = tok[1:-1]
            result.append(tok)
        return result
    return shlex.split(command)
