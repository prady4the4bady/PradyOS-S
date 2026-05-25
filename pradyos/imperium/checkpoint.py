"""IMPERIUM StateCore — checkpoint and resume support.

Phase 0 implementation: JSONL file on disk, one record per task state
mutation. Resume reads back the latest line per task_id.

Phase 3 replaces this with a transactional store; the public API stays
identical so other planes do not break.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pradyos.core.types import TaskState
from pradyos.imperium.task import ImperiumTask, TaskRecord


_DEFAULT_STATE_DIR = Path(
    os.environ.get(
        "PRADYOS_STATE_PATH",
        Path(__file__).resolve().parents[2] / "var" / "state",
    )
)


class CheckpointStore:
    def __init__(self, state_dir: Path | str = _DEFAULT_STATE_DIR) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "imperium_tasks.jsonl"
        self._lock = threading.Lock()

    def write(self, rec: TaskRecord) -> None:
        line = {
            "task_id": rec.spec.task_id,
            "state": rec.state.value,
            "attempts": rec.attempts,
            "kind": rec.spec.kind,
            "priority": rec.spec.priority.value,
            "intent": rec.spec.intent,
            "depends_on": list(rec.spec.depends_on),
            "submitted_by": rec.spec.submitted_by,
            "queued_at": rec.queued_at,
            "started_at": rec.started_at,
            "finished_at": rec.finished_at,
            "last_error": rec.last_error,
            "escalation_reason": rec.escalation_reason,
            "escalation_rule": rec.escalation_rule,
            "payload": rec.spec.payload,
            "max_retries": rec.spec.max_retries,
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, separators=(",", ":")) + "\n")

    def load_latest(self) -> dict[str, dict[str, Any]]:
        """Return the latest checkpoint line per task_id."""
        latest: dict[str, dict[str, Any]] = {}
        if not self.path.exists():
            return latest
        with self._lock:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    latest[rec["task_id"]] = rec
        return latest

    def resume_non_terminal(self) -> list[TaskRecord]:
        """Rebuild ``TaskRecord``s for tasks not in a terminal state."""
        from pradyos.core.types import Priority

        out: list[TaskRecord] = []
        for tid, line in self.load_latest().items():
            try:
                state = TaskState(line["state"])
            except ValueError:
                continue
            if state.terminal:
                continue
            try:
                priority = Priority(line.get("priority", "OPERATIONAL"))
            except ValueError:
                priority = Priority.OPERATIONAL
            spec = ImperiumTask(
                kind=line["kind"],
                payload=line.get("payload", {}),
                intent=line.get("intent", ""),
                priority=priority,
                depends_on=list(line.get("depends_on", [])),
                max_retries=int(line.get("max_retries", 0)),
                submitted_by=line.get("submitted_by", "system"),
                task_id=tid,
            )
            rec = TaskRecord(
                spec=spec,
                state=TaskState.QUEUED,   # resume from queued; runtime decides next move
                attempts=int(line.get("attempts", 0)),
                queued_at=float(line.get("queued_at") or 0.0),
                started_at=None,
                finished_at=None,
                last_error=line.get("last_error"),
                escalation_reason=line.get("escalation_reason"),
                escalation_rule=line.get("escalation_rule"),
            )
            out.append(rec)
        return out
