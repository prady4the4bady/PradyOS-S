from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class DomainEvent:
    aggregate_id: str
    event_type: str
    payload: dict
    version: int
    occurred_at: float

    def to_dict(self) -> dict:
        return {
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "version": self.version,
            "occurred_at": self.occurred_at,
        }


class AggregateRoot:
    def __init__(self, aggregate_id: str) -> None:
        self.aggregate_id = aggregate_id
        self._state: dict = {}
        self._events: list[DomainEvent] = []
        self._version: int = 0
        self._lock = threading.Lock()

    def apply(self, event_type: str, payload: dict) -> DomainEvent:
        with self._lock:
            self._version += 1
            event = DomainEvent(
                aggregate_id=self.aggregate_id,
                event_type=event_type,
                payload=dict(payload) if payload else {},
                version=self._version,
                occurred_at=time.time(),
            )
            self._events.append(event)
            # Shallow merge of payload into state
            self._state.update(event.payload)
            return event

    def get_state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def get_events(self, since_version: int = 0) -> list[DomainEvent]:
        with self._lock:
            events = [e for e in self._events if e.version > since_version]
        return sorted(events, key=lambda e: e.version)

    def rebuild_state(self, events: list[DomainEvent]) -> None:
        with self._lock:
            self._state = {}
            self._events = []
            self._version = 0
            for event in sorted(events, key=lambda e: e.version):
                self._version = event.version
                self._state.update(event.payload)
                self._events.append(event)

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def event_count(self) -> int:
        with self._lock:
            return len(self._events)


class AggregateRegistry:
    def __init__(self) -> None:
        self._aggregates: dict[str, AggregateRoot] = {}
        self._lock = threading.Lock()

    def get_or_create(self, aggregate_id: str) -> AggregateRoot:
        with self._lock:
            agg = self._aggregates.get(aggregate_id)
            if agg is None:
                agg = AggregateRoot(aggregate_id)
                self._aggregates[aggregate_id] = agg
            return agg

    def get(self, aggregate_id: str) -> AggregateRoot | None:
        with self._lock:
            return self._aggregates.get(aggregate_id)

    def list_aggregates(self) -> list[dict]:
        with self._lock:
            ids = sorted(self._aggregates.keys())
            out = []
            for aid in ids:
                agg = self._aggregates[aid]
                # Use the aggregate's own lock-safe accessors.
                out.append({
                    "aggregate_id": agg.aggregate_id,
                    "version": agg.version,
                    "event_count": agg.event_count(),
                    "state_keys": len(agg.get_state()),
                })
            return out

    def delete(self, aggregate_id: str) -> bool:
        with self._lock:
            return self._aggregates.pop(aggregate_id, None) is not None

    def count(self) -> int:
        with self._lock:
            return len(self._aggregates)
