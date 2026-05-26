"""IMPERIUM — SelfHealEngine (Phase 11).

When a task exhausts its retry budget IMPERIUM hands control here.
SelfHealEngine:

1. Loads the latest system snapshot from SnapshotStore (provides a
   "rolled-back-to" reference point for audit / ORACLE investigation).
2. Calls ``kernel.rollback(task_id)`` — raises TaskNotFound if the task
   is unknown.
3. Adds the task_id to the in-memory quarantine set *and* persists it to
   ``var/state/quarantine.json`` so restarts retain the list.
4. Publishes a ``system.self_heal`` bus event so WARDEN (which listens on
   ``system.*``) raises an incident automatically.
5. Writes a structured audit entry.

Double-healing the same task is idempotent (quarantine.add is a set
operation; bus + audit still fire so the event trail is complete).

``release_quarantine`` is a Sovereign-only action (called from the
Sovereign REPL / CLI); it removes the task from the quarantine set and
persists the updated list.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pradyos.core.audit import AuditLog, get_audit_log
from pradyos.core.bus import EventBus, get_bus
from pradyos.core.snapshot import SnapshotStore
from pradyos.imperium.exceptions import TaskNotFound

_DEFAULT_STATE_DIR = Path(
    os.environ.get(
        "PRADYOS_STATE_PATH",
        Path(__file__).resolve().parents[2] / "var" / "state",
    )
)

_QUARANTINE_FILENAME = "quarantine.json"


@dataclass
class HealResult:
    """Returned by :meth:`SelfHealEngine.heal`."""

    task_id: str
    action_taken: str
    rolled_back_to: str | None   # snapshot_id (ts as string) or "none"
    quarantined: bool


class SelfHealEngine:
    """Autonomous self-healing sub-system for IMPERIUM.

    Parameters
    ----------
    kernel:
        The :class:`~pradyos.imperium.kernel.Imperium` instance.
        Must expose a ``rollback(task_id)`` method.
    bus:
        :class:`~pradyos.core.bus.EventBus` (or compatible).
        Falls back to the process-global bus singleton.
    snapshot_store:
        :class:`~pradyos.core.snapshot.SnapshotStore` used to look up
        the latest system snapshot (the "rolled-back-to" reference).
        Falls back to a default SnapshotStore.
    audit:
        :class:`~pradyos.core.audit.AuditLog` for structured ledger
        entries.  Falls back to the process-global audit log.
    """

    AGENT_ID = "imperium.self_heal"

    def __init__(
        self,
        kernel: Any,
        bus: EventBus | None = None,
        snapshot_store: SnapshotStore | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._kernel = kernel
        self._bus: EventBus = bus or get_bus()
        self._snapshot_store: SnapshotStore = snapshot_store or SnapshotStore()
        self._audit: AuditLog = audit or get_audit_log()

        # Derive the quarantine file path from the same env-var the rest
        # of the codebase uses, so tests can override via tmp_state fixture.
        state_dir = Path(
            os.environ.get(
                "PRADYOS_STATE_PATH",
                Path(__file__).resolve().parents[2] / "var" / "state",
            )
        )
        self._quarantine_path: Path = state_dir / _QUARANTINE_FILENAME

        # In-memory quarantine (hot-path reads; disk is the durable copy).
        self._quarantine: set[str] = set()
        self._load_quarantine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def heal(self, task_id: str, reason: str = "retry_budget_exhausted") -> HealResult:
        """Perform an autonomous self-heal cycle for *task_id*.

        Steps
        -----
        1. Load the latest snapshot from the SnapshotStore.
        2. Call ``kernel.rollback(task_id)`` — propagates :exc:`TaskNotFound`
           if the task is unknown.
        3. Add *task_id* to the quarantine set (idempotent) and persist.
        4. Publish ``system.self_heal`` bus event.
        5. Write audit entry.

        Returns
        -------
        HealResult
            Describes the action taken, the snapshot reference, and
            whether the task is now quarantined.

        Raises
        ------
        TaskNotFound
            If *task_id* is not known to the kernel.
        """
        # 1. Latest snapshot — used as "rolled_back_to" reference.
        snaps = self._snapshot_store.latest(1)
        snapshot_id: str = str(snaps[0].ts) if snaps else "none"

        # 2. Kernel rollback — may raise TaskNotFound.
        self._kernel.rollback(task_id)

        # 3. Quarantine (idempotent set operation).
        self._quarantine.add(task_id)
        self._persist_quarantine()

        # 4. Bus event — WARDEN listens on system.* and raises an incident.
        ts = time.time()
        self._bus.publish("system.self_heal", {
            "task_id": task_id,
            "reason": reason,
            "snapshot_id": snapshot_id,
            "ts": ts,
        })

        # 5. Audit entry.
        self._audit.record(
            agent_id=self.AGENT_ID,
            kind="recovery",
            summary=f"self-heal: task {task_id[:8]} quarantined ({reason})",
            detail={
                "task_id": task_id,
                "reason": reason,
                "snapshot_id": snapshot_id,
                "ts": ts,
            },
            correlation_id=task_id,
        )

        return HealResult(
            task_id=task_id,
            action_taken="rollback_and_quarantine",
            rolled_back_to=snapshot_id,
            quarantined=True,
        )

    def is_quarantined(self, task_id: str) -> bool:
        """Return True if *task_id* is currently quarantined."""
        return task_id in self._quarantine

    def release_quarantine(self, task_id: str) -> None:
        """Remove *task_id* from quarantine.

        **Sovereign-only action.** Call from the Sovereign REPL / CLI after
        investigating the root cause of the failure.
        """
        self._quarantine.discard(task_id)
        self._persist_quarantine()

    def quarantine_list(self) -> list[str]:
        """Return a snapshot of all currently quarantined task IDs."""
        return list(self._quarantine)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_quarantine(self) -> None:
        """Populate in-memory set from the persisted JSON file (if it exists)."""
        if not self._quarantine_path.exists():
            return
        try:
            raw = self._quarantine_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            loaded = data.get("quarantine", [])
            if isinstance(loaded, list):
                self._quarantine = set(loaded)
        except (json.JSONDecodeError, OSError, TypeError):
            # Corrupt or unreadable file — start fresh; next persist overwrites.
            self._quarantine = set()

    def _persist_quarantine(self) -> None:
        """Write the current quarantine set to disk as JSON."""
        self._quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"quarantine": sorted(self._quarantine)},
            indent=2,
        )
        self._quarantine_path.write_text(payload, encoding="utf-8")
