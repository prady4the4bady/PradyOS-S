from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field


@dataclass
class HistoryEntry:
    at: float
    from_state: str
    to_state: str
    trigger: str
    context_snapshot: dict

    def to_dict(self) -> dict:
        return {
            "at": self.at,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "trigger": self.trigger,
            "context_snapshot": dict(self.context_snapshot),
        }


@dataclass
class ProcessInstance:
    process_id: str
    process_name: str
    state: str
    context: dict
    history: list[HistoryEntry]
    created_at: float
    updated_at: float

    def to_dict(self) -> dict:
        return {
            "process_id": self.process_id,
            "process_name": self.process_name,
            "state": self.state,
            "context": dict(self.context),
            "history": [h.to_dict() for h in self.history],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProcessManager:
    CAPACITY = 500

    def __init__(self) -> None:
        self._instances: deque[ProcessInstance] = deque(maxlen=self.CAPACITY)
        self._index: dict[str, ProcessInstance] = {}
        self._lock = threading.Lock()

    # ── create ───────────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        initial_state: str,
        context: dict | None = None,
    ) -> ProcessInstance:
        now = time.time()
        inst = ProcessInstance(
            process_id=str(uuid.uuid4()),
            process_name=name,
            state=initial_state,
            context=dict(context) if context else {},
            history=[],
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            # Capture any instance about to be evicted to keep the index consistent.
            evicted: ProcessInstance | None = None
            if len(self._instances) == self._instances.maxlen:
                evicted = self._instances[0]
            self._instances.append(inst)
            self._index[inst.process_id] = inst
            if evicted is not None and evicted.process_id != inst.process_id:
                self._index.pop(evicted.process_id, None)
        return inst

    # ── transition ───────────────────────────────────────────────────────────

    def transition(
        self,
        process_id: str,
        trigger: str,
        new_state: str,
        context_patch: dict | None = None,
    ) -> ProcessInstance | None:
        with self._lock:
            inst = self._index.get(process_id)
            if inst is None:
                return None
            from_state = inst.state
            if context_patch:
                inst.context.update(context_patch)
            entry = HistoryEntry(
                at=time.time(),
                from_state=from_state,
                to_state=new_state,
                trigger=trigger,
                context_snapshot=dict(inst.context),  # AFTER patch
            )
            inst.history.append(entry)
            inst.state = new_state
            inst.updated_at = time.time()
            return inst

    # ── introspection ────────────────────────────────────────────────────────

    def get(self, process_id: str) -> ProcessInstance | None:
        with self._lock:
            return self._index.get(process_id)

    def list_processes(
        self,
        state: str | None = None,
        limit: int = 50,
    ) -> list[ProcessInstance]:
        capped = max(0, min(self.CAPACITY, int(limit)))
        with self._lock:
            snapshot = list(self._instances)
        if state is not None:
            snapshot = [i for i in snapshot if i.state == state]
        snapshot.sort(key=lambda i: i.updated_at, reverse=True)
        return snapshot[:capped]

    def delete(self, process_id: str) -> bool:
        with self._lock:
            inst = self._index.pop(process_id, None)
            if inst is None:
                return False
            try:
                self._instances.remove(inst)
            except ValueError:
                pass
            return True

    def count(self, state: str | None = None) -> int:
        with self._lock:
            if state is None:
                return len(self._instances)
            return sum(1 for i in self._instances if i.state == state)
