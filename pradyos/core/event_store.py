from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from pradyos.core.snapshot_store import SnapshotStore


@dataclass
class Event:
    id: str
    stream: str
    event_type: str
    payload: dict
    sequence: int
    occurred_at: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "stream": self.stream,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "sequence": self.sequence,
            "occurred_at": self.occurred_at,
        }


class EventStore:
    _NS = "event_store"

    def __init__(self, snapshot_store: "SnapshotStore | None" = None) -> None:
        self._store = snapshot_store
        self._streams: dict[str, list[Event]] = {}
        self._lock = threading.Lock()
        if self._store is not None:
            self._load()

    # ── append ───────────────────────────────────────────────────────────────

    def append(self, stream: str, event_type: str, payload: dict) -> Event:
        with self._lock:
            existing = self._streams.setdefault(stream, [])
            event = Event(
                id=uuid.uuid4().hex,
                stream=stream,
                event_type=event_type,
                payload=dict(payload) if payload else {},
                sequence=len(existing) + 1,
                occurred_at=time.time(),
            )
            existing.append(event)
            self._save_locked(stream)
        return event

    # ── read / project ───────────────────────────────────────────────────────

    def read(self, stream: str, from_seq: int = 0) -> list[Event]:
        with self._lock:
            events = self._streams.get(stream)
            if events is None:
                return []
            return [e for e in events if e.sequence > from_seq]

    def project(
        self,
        stream: str,
        reducer: Callable[[dict, Event], dict],
        initial: dict | None = None,
    ) -> dict:
        state = dict(initial) if initial else {}
        with self._lock:
            events = list(self._streams.get(stream) or [])
        for event in events:
            state = reducer(state, event)
        return state

    # ── introspection ────────────────────────────────────────────────────────

    def stream_names(self) -> list[str]:
        with self._lock:
            return sorted(self._streams.keys())

    def event_count(self, stream: str | None = None) -> int:
        with self._lock:
            if stream is not None:
                return len(self._streams.get(stream, []))
            return sum(len(evs) for evs in self._streams.values())

    # ── persistence ──────────────────────────────────────────────────────────

    def _save_locked(self, stream: str) -> None:
        """Caller holds self._lock."""
        if self._store is None:
            return
        try:
            events = self._streams.get(stream, [])
            data = {"events": [e.to_dict() for e in events]}
            self._store.save(self._NS, stream, data)
        except Exception:
            pass

    def _load(self) -> None:
        if self._store is None:
            return
        try:
            keys_info = self._store.list_keys(self._NS)
        except Exception:
            return
        for key_info in keys_info:
            stream = key_info.get("key")
            if not stream:
                continue
            try:
                snap = self._store.get(self._NS, stream)
            except Exception:
                continue
            if snap is None:
                continue
            data = snap.data if hasattr(snap, "data") else snap
            events_raw = data.get("events", []) if isinstance(data, dict) else []
            restored: list[Event] = []
            for ev in events_raw:
                try:
                    restored.append(Event(
                        id=ev["id"],
                        stream=ev["stream"],
                        event_type=ev["event_type"],
                        payload=dict(ev.get("payload") or {}),
                        sequence=int(ev["sequence"]),
                        occurred_at=float(ev["occurred_at"]),
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
            if restored:
                self._streams[stream] = restored
