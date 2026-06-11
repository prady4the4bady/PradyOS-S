"""TITAN OPS — async execution layer (Phase 1).

Wraps the synchronous ``TitanExecutor`` in a true asyncio coroutine
interface so IMPERIUM can fire multiple instructions concurrently without
blocking the event loop.

Design:
    - ``AsyncTitanExecutor.execute()`` is a coroutine that runs the sync
      executor in a thread pool, preserving full audit/bus semantics.
    - ``SnapshotMixin`` captures state before destructive instructions and
      attaches the ``StateSnapshot`` to the ``RollbackEntry``.
    - ``DiffCaptureMixin`` reads file content before/after file-write ops
      and stores a ``DiffCapture`` in the entry.
    - The combined ``AsyncTitanExecutor`` inherits both mixins.

Usage::

    executor = AsyncTitanExecutor()
    result = await executor.execute(instr)         # single
    results = await executor.execute_many(instrs)  # concurrent batch
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from pathlib import Path

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.core.bus import EventBus, get_bus
from pradyos.core.constitution import Constitution, default_constitution
from pradyos.titan_ops.executor import ExecutionResult, TitanExecutor
from pradyos.titan_ops.instruction import InstructionKind, TitanInstruction
from pradyos.titan_ops.rollback import (
    DiffCapture,
    HookKind,
    RollbackEntry,
    RollbackRegistry,
    StateSnapshot,
)

# ---------------------------------------------------------------------------
# Destructive op classification
# ---------------------------------------------------------------------------

_DESTRUCTIVE_SHELL_PREFIXES = (
    "rm ",
    "rmdir",
    "del ",
    "format ",
    "mkfs",
    "dd if=",
    "shred",
    "wipe",
)
_DESTRUCTIVE_KINDS = {InstructionKind.PACKAGE, InstructionKind.SERVICE}


def _is_destructive(instr: TitanInstruction) -> bool:
    if instr.kind in _DESTRUCTIVE_KINDS:
        return True
    if instr.kind is InstructionKind.FILE:
        op = (instr.args or {}).get("op", "")
        return op in {"remove", "remove_tree", "write", "chmod", "chown"}
    if instr.kind is InstructionKind.SHELL and instr.command:
        cmd = instr.command.lower().strip()
        return any(cmd.startswith(p) for p in _DESTRUCTIVE_SHELL_PREFIXES)
    return False


def _affected_paths(instr: TitanInstruction) -> list[str]:
    """Return file paths that will be mutated — for snapshot/diff capture."""
    if instr.kind is InstructionKind.FILE:
        path = (instr.args or {}).get("path")
        return [path] if path else []
    return []


# ---------------------------------------------------------------------------
# Async executor
# ---------------------------------------------------------------------------


class AsyncTitanExecutor:
    """Async wrapper around TitanExecutor with snapshot + diff capture."""

    AGENT_ID = "titan_ops"

    def __init__(
        self,
        audit: AuditLog | None = None,
        constitution: Constitution | None = None,
        bus: EventBus | None = None,
        rollback_registry: RollbackRegistry | None = None,
        max_workers: int = 8,
    ) -> None:
        self.sync_executor = TitanExecutor(
            audit=audit or get_audit_log(),
            constitution=constitution or default_constitution(),
            bus=bus or get_bus(),
            rollback_registry=rollback_registry or RollbackRegistry(),
        )
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="titan-async",
        )

    @property
    def rollback(self) -> RollbackRegistry:
        return self.sync_executor.rollback

    # ---------- public coroutines ----------

    async def execute(self, instr: TitanInstruction) -> ExecutionResult:
        """Execute one instruction asynchronously.

        Captures a state snapshot before destructive ops and attaches the
        snapshot to the rollback entry after execution.
        """
        snapshot: StateSnapshot | None = None
        diffs_before: dict[str, str | None] = {}

        paths = _affected_paths(instr)

        if _is_destructive(instr) and paths:
            # Capture snapshot in the executor thread pool to avoid blocking
            loop = asyncio.get_running_loop()
            snapshot = await loop.run_in_executor(
                self._pool,
                lambda: StateSnapshot.capture(paths),
            )
            # Read before-content for diff capture
            for p in paths:
                try:
                    diffs_before[p] = Path(p).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    diffs_before[p] = None

        # Run the sync executor in the thread pool
        loop = asyncio.get_running_loop()
        result: ExecutionResult = await loop.run_in_executor(
            self._pool,
            self.sync_executor.execute,
            instr,
        )

        # Post-execution: capture diffs + upgrade rollback entry
        if result.succeeded and paths:
            diffs: list[DiffCapture] = []
            for p in paths:
                before = diffs_before.get(p)
                try:
                    after = Path(p).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    after = None
                if before is not None or after is not None:
                    diffs.append(DiffCapture.compute(p, before, after))

            # Upgrade the rollback entry that the sync executor registered
            entry = self.rollback.get(instr.instruction_id)
            if entry is not None:
                entry.snapshot = snapshot
                entry.diffs = diffs
                entry.kind = HookKind.SNAPSHOT if snapshot else HookKind.FILE_DIFF
                self.rollback.register(entry)  # re-register to trigger flush
            elif snapshot or diffs:
                # No hook was registered (no rollback_hook string) — create one
                hook_entry = RollbackEntry(
                    instruction_id=instr.instruction_id,
                    correlation_id=instr.correlation_id,
                    hook=f"snapshot:{snapshot.snapshot_id}" if snapshot else "file_diff",
                    kind=HookKind.SNAPSHOT if snapshot else HookKind.FILE_DIFF,
                    snapshot=snapshot,
                    diffs=diffs,
                )
                self.rollback.register(hook_entry)

        return result

    async def execute_many(
        self,
        instrs: list[TitanInstruction],
        *,
        max_concurrent: int = 4,
    ) -> list[ExecutionResult]:
        """Execute multiple instructions with bounded concurrency.

        Instructions are dispatched as a batch; results are returned in the
        same order as the input list.
        """
        sem = asyncio.Semaphore(max_concurrent)

        async def _guarded(instr: TitanInstruction) -> ExecutionResult:
            async with sem:
                return await self.execute(instr)

        return list(await asyncio.gather(*[_guarded(i) for i in instrs]))

    def close(self) -> None:
        self._pool.shutdown(wait=False)

    def __del__(self) -> None:
        try:
            self._pool.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
