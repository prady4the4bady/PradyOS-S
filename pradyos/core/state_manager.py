from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pradyos.core.snapshot_store import SnapshotStore


class StateManager:
    def __init__(self, snapshot_store: SnapshotStore | None = None) -> None:
        self._store = snapshot_store
        self._hooks: list[tuple[str, Callable[[], Any]]] = []
        self._lock = threading.Lock()
        self._registered_modules: list[str] = []

    def register_module(self, module_name: str) -> None:
        with self._lock:
            if module_name not in self._registered_modules:
                self._registered_modules.append(module_name)

    def save_state(self, module: str, key: str, data: dict) -> dict | None:
        if self._store is None:
            return None
        snap = self._store.save(namespace=module, key=key, data=data)
        return snap.to_dict()

    def load_state(
        self,
        module: str,
        key: str,
        version: int | None = None,
    ) -> dict | None:
        if self._store is None:
            return None
        snap = self._store.get(namespace=module, key=key, version=version)
        if snap is None:
            return None
        return snap.to_dict()

    def register_hook(self, name: str, fn: Callable[[], Any]) -> None:
        with self._lock:
            self._hooks.append((name, fn))

    def shutdown(self) -> list[str]:
        with self._lock:
            hooks_snapshot = list(self._hooks)
        results: list[str] = []
        for name, fn in hooks_snapshot:
            try:
                fn()
                results.append(f"{name}:ok")
            except Exception as exc:
                results.append(f"{name}:error:{exc}")
        return results

    def status(self) -> dict:
        with self._lock:
            return {
                "store_connected": self._store is not None,
                "registered_modules": list(self._registered_modules),
                "hook_count": len(self._hooks),
            }
