from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


_SYNC_FLAG = "__synced__"


@dataclass
class SyncPeer:
    id: str
    broker_name: str
    topics: list[str]
    subscription_ids: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "broker_name": self.broker_name,
            "topics": list(self.topics),
        }


@dataclass
class SyncSession:
    id: str
    peer_a: SyncPeer
    peer_b: SyncPeer
    created_at: float
    active: bool
    synced_count: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "peer_a": self.peer_a.to_dict(),
            "peer_b": self.peer_b.to_dict(),
            "created_at": self.created_at,
            "active": self.active,
            "synced_count": self.synced_count,
        }


class StateSyncManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SyncSession] = {}
        self._brokers: dict[str, Any] = {}
        self._lock = threading.Lock()

    # ── broker registry ──────────────────────────────────────────────────────

    def register_broker(self, name: str, broker: Any) -> None:
        with self._lock:
            self._brokers[name] = broker

    # ── session lifecycle ────────────────────────────────────────────────────

    def create_session(
        self,
        broker_a_name: str,
        broker_b_name: str,
        topics_a: list[str],
        topics_b: list[str],
    ) -> SyncSession:
        with self._lock:
            if broker_a_name not in self._brokers:
                raise ValueError(f"unknown broker: {broker_a_name}")
            if broker_b_name not in self._brokers:
                raise ValueError(f"unknown broker: {broker_b_name}")
            broker_a = self._brokers[broker_a_name]
            broker_b = self._brokers[broker_b_name]

        peer_a = SyncPeer(
            id=uuid.uuid4().hex,
            broker_name=broker_a_name,
            topics=list(topics_a),
            subscription_ids=[],
        )
        peer_b = SyncPeer(
            id=uuid.uuid4().hex,
            broker_name=broker_b_name,
            topics=list(topics_b),
            subscription_ids=[],
        )
        session = SyncSession(
            id=uuid.uuid4().hex,
            peer_a=peer_a,
            peer_b=peer_b,
            created_at=time.time(),
            active=True,
            synced_count=0,
        )

        # Forward broker_a → broker_b for each topic in topics_a
        for topic in topics_a:
            cb = self._make_forwarder(session, topic, broker_b)
            sub = broker_a.subscribe(topic, cb)
            peer_a.subscription_ids.append(sub.id)

        # Forward broker_b → broker_a for each topic in topics_b
        for topic in topics_b:
            cb = self._make_forwarder(session, topic, broker_a)
            sub = broker_b.subscribe(topic, cb)
            peer_b.subscription_ids.append(sub.id)

        with self._lock:
            self._sessions[session.id] = session

        return session

    def _make_forwarder(self, session: SyncSession, topic: str, target_broker: Any):
        """Build a callback that forwards messages to target_broker on `topic`,
        with cycle detection via the _SYNC_FLAG sentinel key."""

        def _cb(message: dict) -> None:
            # Cycle guard: already a syncing-message → do not re-forward.
            if isinstance(message, dict) and message.get(_SYNC_FLAG):
                return
            try:
                if isinstance(message, dict):
                    forwarded = {**message, _SYNC_FLAG: True}
                else:
                    forwarded = {"value": message, _SYNC_FLAG: True}
                target_broker.publish(topic, forwarded)
                session.synced_count += 1
            except Exception:
                # Broker hiccups never crash the sync callback.
                pass

        return _cb

    def stop_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            broker_a = self._brokers.get(session.peer_a.broker_name)
            broker_b = self._brokers.get(session.peer_b.broker_name)

        if broker_a is not None:
            for sid in session.peer_a.subscription_ids:
                try:
                    broker_a.unsubscribe(sid)
                except Exception:
                    pass
        if broker_b is not None:
            for sid in session.peer_b.subscription_ids:
                try:
                    broker_b.unsubscribe(sid)
                except Exception:
                    pass

        session.active = False
        return True

    # ── introspection ────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> SyncSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self, active_only: bool = False) -> list[SyncSession]:
        with self._lock:
            sessions = list(self._sessions.values())
        if active_only:
            sessions = [s for s in sessions if s.active]
        sessions.sort(key=lambda s: s.created_at)
        return sessions

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
