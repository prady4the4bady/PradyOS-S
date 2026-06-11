from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Snapshot:
    namespace: str
    key: str
    version: int
    data: dict
    saved_at: float

    def to_dict(self) -> dict:
        return {
            "namespace": self.namespace,
            "key": self.key,
            "version": self.version,
            "data": self.data,
            "saved_at": self.saved_at,
        }


class SnapshotStore:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir is not None else None
        # _store[namespace][key][version] = Snapshot
        self._store: dict[str, dict[str, dict[int, Snapshot]]] = {}
        self._lock = threading.Lock()

        if self._base_dir is not None:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        if self._base_dir is None:
            return
        for jsonl_file in sorted(self._base_dir.glob("*.jsonl")):
            namespace = jsonl_file.stem  # noqa: F841
            with jsonl_file.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        snap = Snapshot(
                            namespace=rec["namespace"],
                            key=rec["key"],
                            version=int(rec["version"]),
                            data=rec["data"],
                            saved_at=float(rec["saved_at"]),
                        )
                        if snap.namespace not in self._store:
                            self._store[snap.namespace] = {}
                        if snap.key not in self._store[snap.namespace]:
                            self._store[snap.namespace][snap.key] = {}
                        self._store[snap.namespace][snap.key][snap.version] = snap
                    except (KeyError, ValueError, json.JSONDecodeError):
                        continue

    def save(self, namespace: str, key: str, data: dict) -> Snapshot:
        with self._lock:
            if namespace not in self._store:
                self._store[namespace] = {}
            if key not in self._store[namespace]:
                self._store[namespace][key] = {}
            existing = self._store[namespace][key]
            version = max(existing.keys()) + 1 if existing else 1
            snap = Snapshot(
                namespace=namespace,
                key=key,
                version=version,
                data=data,
                saved_at=time.time(),
            )
            self._store[namespace][key][version] = snap
            if self._base_dir is not None:
                jsonl_path = self._base_dir / f"{namespace}.jsonl"
                with jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(snap.to_dict()) + "\n")
        return snap

    def get(self, namespace: str, key: str, version: int | None = None) -> Snapshot | None:
        with self._lock:
            if namespace not in self._store:
                return None
            if key not in self._store[namespace]:
                return None
            versions = self._store[namespace][key]
            if not versions:
                return None
            if version is None:
                return versions[max(versions.keys())]
            return versions.get(version)

    def list_keys(self, namespace: str) -> list[dict]:
        with self._lock:
            if namespace not in self._store:
                return []
            result = []
            for key in sorted(self._store[namespace].keys()):
                versions = self._store[namespace][key]
                if not versions:
                    continue
                latest_ver = max(versions.keys())
                result.append(
                    {
                        "key": key,
                        "versions": len(versions),
                        "latest_version": latest_ver,
                        "latest_saved_at": versions[latest_ver].saved_at,
                    }
                )
            return result

    def delete(self, namespace: str, key: str) -> bool:
        with self._lock:
            if namespace not in self._store:
                return False
            if key not in self._store[namespace]:
                return False
            del self._store[namespace][key]
            return True

    def count(self, namespace: str | None = None) -> int:
        with self._lock:
            if namespace is not None:
                if namespace not in self._store:
                    return 0
                return sum(len(v) for v in self._store[namespace].values())
            return sum(len(v) for ns_data in self._store.values() for v in ns_data.values())
