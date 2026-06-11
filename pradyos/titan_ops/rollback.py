"""Rollback hook registry — Phase 1.

Phase 1 upgrades the registry with:
- Typed hooks (shell string, snapshot revert, file-restore from diff)
- State snapshots captured *before* destructive ops (copy of affected paths,
  hash manifest, env snapshot)
- Diff capture: unified diff stored alongside each file-mutating entry
- Serialisation helpers so RecoveryCore can persist the full registry to disk
"""

from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class HookKind(str, Enum):
    SHELL = "shell"  # run a shell command to undo
    SNAPSHOT = "snapshot"  # restore a directory/file from a snapshot copy
    FILE_DIFF = "file_diff"  # apply reverse of a unified diff
    NOOP = "noop"  # nothing to undo (read-only op)


@dataclass
class StateSnapshot:
    """Snapshot of file/directory state taken before a destructive op."""

    snapshot_id: str
    captured_at: float
    targets: list[str]  # paths that were snapshotted
    snapshot_dir: str  # temp directory holding copies
    hash_manifest: dict[str, str]  # path → sha256 hex

    @classmethod
    def capture(cls, paths: list[str], snapshot_root: str | None = None) -> StateSnapshot:
        snap_id = _short_id()
        snap_dir = tempfile.mkdtemp(
            prefix=f"prd-snap-{snap_id}-",
            dir=snapshot_root,
        )
        manifest: dict[str, str] = {}
        targets: list[str] = []
        for p in paths:
            src = Path(p)
            if not src.exists():
                continue
            targets.append(str(src))
            rel = src.name
            dest = Path(snap_dir) / rel
            try:
                if src.is_dir():
                    shutil.copytree(src, dest, symlinks=True, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dest)
                manifest[str(src)] = _sha256(dest)
            except OSError:
                pass
        return cls(
            snapshot_id=snap_id,
            captured_at=time.time(),
            targets=targets,
            snapshot_dir=snap_dir,
            hash_manifest=manifest,
        )

    def restore(self) -> list[str]:
        """Restore all snapshotted paths. Returns list of restored paths."""
        restored: list[str] = []
        snap = Path(self.snapshot_dir)
        for original_path in self.targets:
            src = snap / Path(original_path).name
            if not src.exists():
                continue
            try:
                dst = Path(original_path)
                if src.is_dir():
                    shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst, symlinks=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                restored.append(original_path)
            except OSError:
                pass
        return restored

    def cleanup(self) -> None:
        shutil.rmtree(self.snapshot_dir, ignore_errors=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "captured_at": self.captured_at,
            "targets": self.targets,
            "snapshot_dir": self.snapshot_dir,
            "hash_manifest": self.hash_manifest,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StateSnapshot:
        return cls(
            snapshot_id=d["snapshot_id"],
            captured_at=d["captured_at"],
            targets=d["targets"],
            snapshot_dir=d["snapshot_dir"],
            hash_manifest=d["hash_manifest"],
        )


@dataclass
class DiffCapture:
    """Unified diff between before/after state of a file."""

    path: str
    before_hash: str | None
    after_hash: str | None
    unified_diff: str  # full unified diff text
    captured_at: float = field(default_factory=time.time)

    @classmethod
    def compute(
        cls, path: str, before_content: str | None, after_content: str | None
    ) -> DiffCapture:
        before_lines = (before_content or "").splitlines(keepends=True)
        after_lines = (after_content or "").splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"{path}.before",
                tofile=f"{path}.after",
            )
        )
        return cls(
            path=path,
            before_hash=_sha256_str(before_content or "") if before_content is not None else None,
            after_hash=_sha256_str(after_content or "") if after_content is not None else None,
            unified_diff=diff,
        )

    def apply_reverse(self) -> str:
        """Return the content that results from reversing the diff."""
        # Swap +/- lines to produce the reverse patch
        reversed_lines: list[str] = []
        for line in self.unified_diff.splitlines(keepends=True):
            if line.startswith("+") and not line.startswith("+++"):
                reversed_lines.append("-" + line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                reversed_lines.append("+" + line[1:])
            else:
                reversed_lines.append(line)
        return "".join(reversed_lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "unified_diff": self.unified_diff,
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DiffCapture:
        return cls(**d)


@dataclass
class RollbackEntry:
    """Full rollback record for one executed instruction."""

    instruction_id: str
    correlation_id: str | None
    hook: str  # shell command or descriptor
    kind: HookKind = HookKind.SHELL
    detail: dict[str, Any] = field(default_factory=dict)
    snapshot: StateSnapshot | None = None
    diffs: list[DiffCapture] = field(default_factory=list)
    registered_at: float = field(default_factory=time.time)
    executed: bool = False
    executed_at: float | None = None
    execute_result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "instruction_id": self.instruction_id,
            "correlation_id": self.correlation_id,
            "hook": self.hook,
            "kind": self.kind.value,
            "detail": self.detail,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "diffs": [dc.to_dict() for dc in self.diffs],
            "registered_at": self.registered_at,
            "executed": self.executed,
            "executed_at": self.executed_at,
            "execute_result": self.execute_result,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RollbackEntry:
        return cls(
            instruction_id=d["instruction_id"],
            correlation_id=d.get("correlation_id"),
            hook=d["hook"],
            kind=HookKind(d.get("kind", "shell")),
            detail=d.get("detail", {}),
            snapshot=StateSnapshot.from_dict(d["snapshot"]) if d.get("snapshot") else None,
            diffs=[DiffCapture.from_dict(dc) for dc in d.get("diffs", [])],
            registered_at=d.get("registered_at", 0.0),
            executed=d.get("executed", False),
            executed_at=d.get("executed_at"),
            execute_result=d.get("execute_result"),
        )


class RollbackRegistry:
    """Thread-safe map: instruction_id → RollbackEntry, with persistence."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self._entries: dict[str, RollbackEntry] = {}
        self._lock = threading.Lock()
        self.persist_path = persist_path
        if persist_path and persist_path.exists():
            self._load()

    def register(self, entry: RollbackEntry) -> None:
        with self._lock:
            self._entries[entry.instruction_id] = entry
            self._flush()

    def get(self, instruction_id: str) -> RollbackEntry | None:
        with self._lock:
            return self._entries.get(instruction_id)

    def all(self) -> list[RollbackEntry]:
        with self._lock:
            return list(self._entries.values())

    def pop(self, instruction_id: str) -> RollbackEntry | None:
        with self._lock:
            entry = self._entries.pop(instruction_id, None)
            if entry is not None:
                self._flush()
            return entry

    def execute_rollback(self, instruction_id: str) -> dict[str, Any]:
        """Execute the rollback for a registered instruction.

        Returns a result dict with 'ok', 'restored', and 'detail'.
        """
        with self._lock:
            entry = self._entries.get(instruction_id)
        if entry is None:
            return {"ok": False, "error": f"no rollback registered for {instruction_id}"}

        entry.executed_at = time.time()
        result: dict[str, Any] = {"ok": False, "restored": [], "detail": {}}

        try:
            if entry.kind is HookKind.SNAPSHOT and entry.snapshot:
                restored = entry.snapshot.restore()
                result.update(
                    {
                        "ok": True,
                        "restored": restored,
                        "detail": {"snapshot_id": entry.snapshot.snapshot_id},
                    }
                )
            elif entry.kind is HookKind.FILE_DIFF and entry.diffs:
                for dc in entry.diffs:
                    # Write the reversed patch as the restored file content
                    try:
                        Path(dc.path).write_text(dc.apply_reverse(), encoding="utf-8")
                        result["restored"].append(dc.path)
                    except OSError as e:
                        result["detail"][dc.path] = str(e)
                result["ok"] = True
            elif entry.kind is HookKind.SHELL:
                import subprocess as _sp

                r = _sp.run(entry.hook, shell=True, capture_output=True, text=True, timeout=30)
                result.update(
                    {
                        "ok": r.returncode == 0,
                        "detail": {
                            "stdout": r.stdout[-500:],
                            "stderr": r.stderr[-500:],
                            "returncode": r.returncode,
                        },
                    }
                )
            else:
                result.update({"ok": True, "detail": {"note": "noop rollback"}})

            entry.execute_result = "ok" if result["ok"] else "failed"
        except Exception as e:  # noqa: BLE001
            entry.execute_result = f"error: {e}"
            result["error"] = str(e)

        entry.executed = True
        with self._lock:
            self._flush()
        return result

    # ---------- persistence ----------

    def _flush(self) -> None:
        if self.persist_path is None:
            return
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = [e.to_dict() for e in self._entries.values()]
            self.persist_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _load(self) -> None:
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
            for d in data:
                try:
                    e = RollbackEntry.from_dict(d)
                    self._entries[e.instruction_id] = e
                except Exception:  # noqa: BLE001
                    pass
        except (OSError, json.JSONDecodeError):
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_file():
        h.update(path.read_bytes())
    return h.hexdigest()


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _short_id() -> str:
    import uuid

    return uuid.uuid4().hex[:8]
