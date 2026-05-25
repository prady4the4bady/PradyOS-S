"""TITAN OPS subprocess executor.

Translates a ``TitanInstruction`` into an isolated subprocess invocation,
captures stdout/stderr in full, enforces timeout, attributes the run in
the audit log with the constitutional fields (timestamp, agent_id,
command, result, exit_code, rollback_hook), and registers a rollback
entry where one was supplied.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------------------
# Windows-compatible process termination helpers
# ---------------------------------------------------------------------------

_IS_WINDOWS = sys.platform == "win32"


def _kill_tree_graceful(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Send SIGTERM (POSIX) or CTRL_BREAK_EVENT (Windows) to the process tree."""
    if _IS_WINDOWS:
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except (OSError, AttributeError):
            try:
                proc.terminate()
            except OSError:
                pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError, AttributeError):
            pass


def _kill_tree_forceful(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Forcefully kill the process tree."""
    if _IS_WINDOWS:
        try:
            proc.kill()
        except OSError:
            pass
    else:
        try:
            _sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
            os.killpg(proc.pid, _sigkill)
        except (ProcessLookupError, PermissionError, OSError, AttributeError):
            pass


def _popen_kwargs() -> dict:
    """Platform-specific Popen kwargs for process-group isolation."""
    if _IS_WINDOWS:
        # CREATE_NEW_PROCESS_GROUP allows CTRL_BREAK_EVENT targeting
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}
from dataclasses import asdict, dataclass, field
from typing import Any

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.core.bus import EventBus, get_bus
from pradyos.core.constitution import (
    ApprovalDomain,
    Constitution,
    default_constitution,
)
from pradyos.core.ids import new_id
from pradyos.core.types import ExecutionLane
from pradyos.titan_ops.instruction import InstructionKind, TitanInstruction
from pradyos.titan_ops.lanes import lane_for, parse_command
from pradyos.titan_ops.rollback import RollbackEntry, RollbackRegistry


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ExecutionResult:
    instruction_id: str
    agent_id: str
    lane: ExecutionLane
    argv: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    started_at: float
    finished_at: float
    timed_out: bool
    escalated: bool = False
    escalation_reason: str | None = None
    rollback_hook: str | None = None
    correlation_id: str | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return (not self.escalated) and (not self.timed_out) and self.exit_code == 0

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lane"] = self.lane.value
        d["duration_sec"] = self.duration_sec
        d["succeeded"] = self.succeeded
        return d


# ---------------------------------------------------------------------------
# Kind-specific command builders
# ---------------------------------------------------------------------------

def _build_argv(instr: TitanInstruction) -> list[str]:
    """Translate the structured kind+args into an argv list."""
    if instr.kind is InstructionKind.SHELL:
        if not instr.command:
            raise ValueError("shell instruction requires 'command'")
        return parse_command(instr.command)

    if instr.kind is InstructionKind.PACKAGE:
        return _argv_package(instr.args)

    if instr.kind is InstructionKind.FILE:
        return _argv_file(instr.args)

    if instr.kind is InstructionKind.SERVICE:
        return _argv_service(instr.args)

    if instr.kind is InstructionKind.PROCESS:
        return _argv_process(instr.args)

    raise ValueError(f"unsupported instruction.kind: {instr.kind!r}")


def _argv_package(args: dict[str, Any]) -> list[str]:
    manager = args.get("manager", "apt").lower()
    op = args.get("op", "install").lower()
    pkg = args.get("package")
    if not pkg:
        raise ValueError("package instruction requires args.package")
    pkgs = pkg if isinstance(pkg, list) else [pkg]
    if manager == "apt":
        op_map = {"install": ["install", "-y"], "remove": ["remove", "-y"],
                  "purge": ["purge", "-y"], "update": ["update"], "upgrade": ["upgrade", "-y"]}
        return ["apt-get", *op_map.get(op, [op]), *pkgs] if op != "update" else ["apt-get", "update"]
    if manager == "pip":
        op_map = {"install": ["install"], "uninstall": ["uninstall", "-y"], "upgrade": ["install", "-U"]}
        return ["pip", *op_map.get(op, [op]), *pkgs]
    if manager == "dnf" or manager == "yum":
        return [manager, op, "-y", *pkgs]
    if manager == "pacman":
        op_map = {"install": ["-S", "--noconfirm"], "remove": ["-R", "--noconfirm"], "update": ["-Syu", "--noconfirm"]}
        return ["pacman", *op_map.get(op, [op]), *pkgs]
    raise ValueError(f"unsupported package manager: {manager!r}")


def _argv_file(args: dict[str, Any]) -> list[str]:
    op = args.get("op", "stat").lower()
    path = args.get("path")
    if not path:
        raise ValueError("file instruction requires args.path")
    if _IS_WINDOWS:
        # Windows equivalents — use Python itself as the runtime so we need no
        # external Unix tools.  These argv lists are passed to the executor which
        # routes them through Popen; Python is always available as sys.executable.
        _py = sys.executable
        if op == "stat":
            return [_py, "-c",
                    f"import os,json; s=os.stat(r'{path}'); "
                    f"print(json.dumps({{'size':s.st_size,'mtime':s.st_mtime}}))"]
        if op == "read":
            return [_py, "-c", f"import sys; sys.stdout.write(open(r'{path}').read())"]
        if op == "list":
            return [_py, "-c",
                    f"import os; [print(e) for e in os.listdir(r'{path}')]"]
        if op == "remove":
            return [_py, "-c", f"import os; os.remove(r'{path}')"]
        if op == "remove_tree":
            return [_py, "-c",
                    f"import shutil; shutil.rmtree(r'{path}', ignore_errors=False)"]
        if op == "mkdir":
            return [_py, "-c",
                    f"import os; os.makedirs(r'{path}', exist_ok=True)"]
        if op == "chmod":
            mode = args.get("mode")
            if not mode:
                raise ValueError("file.chmod requires args.mode")
            return [_py, "-c",
                    f"import os; os.chmod(r'{path}', 0o{mode})"]
        if op == "chown":
            raise ValueError("file.chown is not supported on Windows")
        if op == "write":
            content = args.get("content", "")
            return [_py, "-c",
                    f"open(r'{path}','w').write({content!r})"]
        raise ValueError(f"unsupported file op: {op!r}")
    # POSIX
    if op == "stat":
        return ["stat", path]
    if op == "read":
        return ["cat", path]
    if op == "list":
        return ["ls", "-la", path]
    if op == "remove":
        return ["rm", "-f", path]
    if op == "remove_tree":
        return ["rm", "-rf", path]  # constitution will flag rm -rf /
    if op == "mkdir":
        return ["mkdir", "-p", path]
    if op == "chmod":
        mode = args.get("mode")
        if not mode:
            raise ValueError("file.chmod requires args.mode")
        return ["chmod", str(mode), path]
    if op == "chown":
        owner = args.get("owner")
        if not owner:
            raise ValueError("file.chown requires args.owner")
        return ["chown", str(owner), path]
    if op == "write":
        content = args.get("content", "")
        # tee handles redirection without needing a shell
        return ["sh", "-c", f"printf %s {shlex.quote(content)} > {shlex.quote(path)}"]
    raise ValueError(f"unsupported file op: {op!r}")


def _argv_service(args: dict[str, Any]) -> list[str]:
    op = args.get("op", "status").lower()
    unit = args.get("unit")
    if not unit:
        raise ValueError("service instruction requires args.unit")
    if _IS_WINDOWS:
        # Map to Windows Service Control Manager via sc.exe
        sc_op_map = {
            "start": "start", "stop": "stop", "restart": None,
            "status": "query", "enable": "config", "disable": "config",
        }
        if op == "restart":
            raise ValueError("service.restart on Windows requires two separate stop/start ops")
        if op in {"enable", "disable"}:
            start_mode = "auto" if op == "enable" else "disabled"
            return ["sc.exe", "config", unit, f"start={start_mode}"]
        sc_op = sc_op_map.get(op)
        if sc_op is None:
            raise ValueError(f"unsupported service op on Windows: {op!r}")
        return ["sc.exe", sc_op, unit]
    if op in {"start", "stop", "restart", "reload", "enable", "disable",
              "status", "mask", "unmask"}:
        return ["systemctl", op, unit]
    raise ValueError(f"unsupported service op: {op!r}")


def _argv_process(args: dict[str, Any]) -> list[str]:
    op = args.get("op", "list").lower()
    _py = sys.executable
    if _IS_WINDOWS:
        if op == "list":
            return [_py, "-c",
                    "import psutil; [print(p.pid, p.name(), p.status()) "
                    "for p in psutil.process_iter(['pid','name','status'])]"]
        if op == "kill":
            pid = args.get("pid")
            if pid is None:
                raise ValueError("process.kill requires args.pid")
            return [_py, "-c",
                    f"import os,signal; os.kill({pid}, signal.SIGTERM)"]
        if op == "tree":
            return [_py, "-c",
                    "import psutil; "
                    "[print(p.pid, p.name()) for p in psutil.process_iter(['pid','name'])]"]
        raise ValueError(f"unsupported process op: {op!r}")
    if op == "list":
        return ["ps", "-eo", "pid,user,%cpu,%mem,comm,args", "--no-headers"]
    if op == "kill":
        pid = args.get("pid")
        sig = args.get("signal", "TERM")
        if pid is None:
            raise ValueError("process.kill requires args.pid")
        return ["kill", f"-{sig}", str(pid)]
    if op == "tree":
        pid = args.get("pid", "")
        return ["pstree", "-p", str(pid)] if pid else ["pstree", "-p"]
    raise ValueError(f"unsupported process op: {op!r}")


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class TitanExecutor:
    """Synchronous subprocess executor with full audit attribution.

    Thread-safe — multiple instructions may be executed in parallel from
    different threads. The executor itself holds no per-request state.
    """

    AGENT_ID = "titan_ops"

    def __init__(
        self,
        audit: AuditLog | None = None,
        constitution: Constitution | None = None,
        bus: EventBus | None = None,
        rollback_registry: RollbackRegistry | None = None,
    ) -> None:
        self.audit = audit or get_audit_log()
        self.constitution = constitution or default_constitution()
        self.bus = bus or get_bus()
        self.rollback = rollback_registry or RollbackRegistry()

    def execute(self, instr: TitanInstruction) -> ExecutionResult:
        argv: list[str]
        try:
            argv = _build_argv(instr)
        except ValueError as e:
            return self._record_error(instr, [], f"build_argv: {e}")

        lane_cfg = lane_for(instr.lane)
        argv = lane_cfg.wrap(argv)
        rendered = " ".join(shlex.quote(a) for a in argv)

        # Constitutional gate — instructions Sovereign-bound do not execute.
        decision = self.constitution.classify(
            kind=f"titan_{instr.kind.value}",
            summary=instr.intent or rendered,
            detail={"command": rendered, "lane": instr.lane.value, "intent": instr.intent},
        )
        if decision.domain is ApprovalDomain.APPROVAL_REQUIRED:
            return self._record_escalation(instr, argv, rendered, decision.reason, decision.matched_rule)

        env = os.environ.copy()
        env.update(lane_cfg.extra_env)
        env.update(instr.env)

        started = time.time()
        timed_out = False
        exit_code: int | None = None
        stdout = ""
        stderr = ""
        error: str | None = None

        try:
            proc = subprocess.Popen(  # noqa: S603 — intentional, audited
                argv,
                cwd=instr.cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **_popen_kwargs(),
            )
            try:
                stdout, stderr = proc.communicate(timeout=instr.timeout_sec)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_tree_graceful(proc)
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    _kill_tree_forceful(proc)
                    stdout, stderr = proc.communicate()
                exit_code = proc.returncode
        except FileNotFoundError as e:
            error = f"binary not found: {e}"
            exit_code = 127
        except PermissionError as e:
            error = f"permission denied: {e}"
            exit_code = 126
        except OSError as e:
            error = f"os error: {e}"
            exit_code = -1
        finally:
            finished = time.time()

        result = ExecutionResult(
            instruction_id=instr.instruction_id,
            agent_id=instr.agent_id,
            lane=instr.lane,
            argv=argv,
            exit_code=exit_code,
            stdout=stdout or "",
            stderr=stderr or "",
            started_at=started,
            finished_at=finished,
            timed_out=timed_out,
            rollback_hook=instr.rollback_hook,
            correlation_id=instr.correlation_id,
            error=error,
        )
        self._record(instr, result, decision_rule=decision.matched_rule)
        if instr.rollback_hook:
            self.rollback.register(
                RollbackEntry(
                    instruction_id=instr.instruction_id,
                    correlation_id=instr.correlation_id,
                    hook=instr.rollback_hook,
                    detail={"argv": argv},
                )
            )
        return result

    # ---------- audit helpers ----------

    def _record(self, instr: TitanInstruction, result: ExecutionResult, decision_rule: str | None) -> None:
        rec = self.audit.record(
            agent_id=instr.agent_id,
            kind="command",
            summary=instr.intent or " ".join(result.argv),
            detail={
                "instruction_id": instr.instruction_id,
                "lane": instr.lane.value,
                "kind": instr.kind.value,
                "argv": result.argv,
                "stdout_tail": (result.stdout or "")[-2000:],
                "stderr_tail": (result.stderr or "")[-2000:],
                "timed_out": result.timed_out,
                "error": result.error,
                "constitutional_rule": decision_rule,
                "duration_sec": result.duration_sec,
                "executed_by": self.AGENT_ID,
            },
            exit_code=result.exit_code,
            rollback_hook=instr.rollback_hook,
            correlation_id=instr.correlation_id,
        )
        self.bus.publish(
            "titan.completed",
            {
                "instruction_id": instr.instruction_id,
                "correlation_id": instr.correlation_id,
                "succeeded": result.succeeded,
                "exit_code": result.exit_code,
                "audit_record_id": rec.record_id,
            },
        )

    def _record_error(self, instr: TitanInstruction, argv: list[str], message: str) -> ExecutionResult:
        now = time.time()
        result = ExecutionResult(
            instruction_id=instr.instruction_id,
            agent_id=instr.agent_id,
            lane=instr.lane,
            argv=argv,
            exit_code=-2,
            stdout="",
            stderr=message,
            started_at=now,
            finished_at=now,
            timed_out=False,
            error=message,
            rollback_hook=instr.rollback_hook,
            correlation_id=instr.correlation_id,
        )
        self.audit.record(
            agent_id=instr.agent_id,
            kind="command",
            summary=f"REJECTED: {instr.intent or instr.command or instr.kind.value}",
            detail={
                "instruction_id": instr.instruction_id,
                "error": message,
                "executed_by": self.AGENT_ID,
            },
            exit_code=-2,
            correlation_id=instr.correlation_id,
        )
        return result

    def _record_escalation(
        self,
        instr: TitanInstruction,
        argv: list[str],
        rendered: str,
        reason: str,
        rule: str | None,
    ) -> ExecutionResult:
        now = time.time()
        result = ExecutionResult(
            instruction_id=instr.instruction_id,
            agent_id=instr.agent_id,
            lane=instr.lane,
            argv=argv,
            exit_code=None,
            stdout="",
            stderr="",
            started_at=now,
            finished_at=now,
            timed_out=False,
            escalated=True,
            escalation_reason=reason,
            rollback_hook=instr.rollback_hook,
            correlation_id=instr.correlation_id,
        )
        rec = self.audit.record(
            agent_id=instr.agent_id,
            kind="command",
            summary=f"ESCALATED: {instr.intent or rendered}",
            detail={
                "instruction_id": instr.instruction_id,
                "argv": argv,
                "constitutional_rule": rule,
                "reason": reason,
                "executed_by": self.AGENT_ID,
            },
            exit_code=None,
            correlation_id=instr.correlation_id,
        )
        self.bus.publish(
            "titan.escalated",
            {
                "instruction_id": instr.instruction_id,
                "correlation_id": instr.correlation_id,
                "reason": reason,
                "rule": rule,
                "audit_record_id": rec.record_id,
                "intent": instr.intent or rendered,
            },
        )
        return result
