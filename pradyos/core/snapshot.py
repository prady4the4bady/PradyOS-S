"""SystemSnapshot — lightweight telemetry snapshots persisted as JSONL.

Captures a point-in-time view of PRADY OS state for monitoring, trend
analysis, and self-healing decisions.

Windows-safe: pathlib only, no AF_UNIX, no fork, thread-safe writes.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "var" / "state" / "snapshots.jsonl"


@dataclass
class SystemSnapshot:
    """Point-in-time view of PRADY OS system state."""

    ts: float = field(default_factory=time.time)
    campaigns_active: int = 0
    campaigns_total: int = 0
    tasks_pending: int = 0
    tasks_running: int = 0
    tasks_completed: int = 0
    incidents_open: int = 0
    memory_records: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SystemSnapshot":
        return cls(
            ts=float(d.get("ts", time.time())),
            campaigns_active=int(d.get("campaigns_active", 0)),
            campaigns_total=int(d.get("campaigns_total", 0)),
            tasks_pending=int(d.get("tasks_pending", 0)),
            tasks_running=int(d.get("tasks_running", 0)),
            tasks_completed=int(d.get("tasks_completed", 0)),
            incidents_open=int(d.get("incidents_open", 0)),
            memory_records=int(d.get("memory_records", 0)),
            metadata=dict(d.get("metadata", {})),
        )


class SnapshotStore:
    """Thread-safe JSONL-backed store of SystemSnapshots.

    Each call to ``record()`` appends one line.  ``latest()`` reads the last N
    lines efficiently by scanning from the end of the file.  ``prune()`` rewrites
    the file keeping only the most recent *keep* entries.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path if path is not None else _DEFAULT_PATH
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, snapshot: SystemSnapshot) -> None:
        """Append *snapshot* to the JSONL file (creates parent dirs)."""
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(snapshot.to_dict(), separators=(",", ":")) + "\n")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def latest(self, n: int = 100) -> list[SystemSnapshot]:
        """Return the most recent *n* snapshots, newest first.

        Reads all lines (JSONL file) and returns the tail.  For long-running
        deployments use ``prune()`` periodically to keep the file small.
        """
        if not self._path.exists():
            return []
        with self._lock:
            try:
                lines = self._path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return []

        tail = lines[-n:] if len(lines) > n else lines
        snapshots: list[SystemSnapshot] = []
        for raw in reversed(tail):  # newest-first
            raw = raw.strip()
            if not raw:
                continue
            try:
                snapshots.append(SystemSnapshot.from_dict(json.loads(raw)))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return snapshots

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def prune(self, keep: int = 1000) -> int:
        """Rewrite the file keeping only the last *keep* entries.

        Returns the number of lines removed.
        """
        if not self._path.exists():
            return 0
        with self._lock:
            try:
                lines = [l for l in self._path.read_text(encoding="utf-8").splitlines() if l.strip()]
            except OSError:
                return 0

            removed = max(0, len(lines) - keep)
            if removed == 0:
                return 0

            kept = lines[-keep:]
            tmp = self._path.with_suffix(".jsonl.tmp")
            tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
            tmp.replace(self._path)
            return removed
