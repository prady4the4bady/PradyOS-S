from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Topic:
    name: str
    created_at: float

    def to_dict(self) -> dict:
        return {"name": self.name, "created_at": self.created_at}


@dataclass
class Subscription:
    id: str
    topic: str
    callback: Callable[[dict], None]
    created_at: float

    def to_dict(self) -> dict:
        # Intentionally omit `callback` — it's not JSON-serializable.
        return {
            "id": self.id,
            "topic": self.topic,
            "created_at": self.created_at,
        }


class PubSubBroker:
    def __init__(self) -> None:
        self._topics: dict[str, Topic] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._topic_subs: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    # ── internal helpers ─────────────────────────────────────────────────────

    def _ensure_topic_locked(self, topic: str) -> None:
        """Caller holds self._lock."""
        if topic not in self._topics:
            self._topics[topic] = Topic(name=topic, created_at=time.time())
            self._topic_subs[topic] = []

    # ── subscribe / unsubscribe ──────────────────────────────────────────────

    def subscribe(self, topic: str, callback: Callable[[dict], None]) -> Subscription:
        sub = Subscription(
            id=uuid.uuid4().hex,
            topic=topic,
            callback=callback,
            created_at=time.time(),
        )
        with self._lock:
            self._ensure_topic_locked(topic)
            self._subscriptions[sub.id] = sub
            self._topic_subs[topic].append(sub.id)
        return sub

    def unsubscribe(self, subscription_id: str) -> bool:
        with self._lock:
            sub = self._subscriptions.pop(subscription_id, None)
            if sub is None:
                return False
            topic_list = self._topic_subs.get(sub.topic, [])
            if subscription_id in topic_list:
                topic_list.remove(subscription_id)
            return True

    # ── publish ──────────────────────────────────────────────────────────────

    def publish(self, topic: str, message: dict) -> int:
        with self._lock:
            self._ensure_topic_locked(topic)
            sub_ids = list(self._topic_subs.get(topic, []))
            callbacks: list[Callable[[dict], None]] = []
            for sid in sub_ids:
                sub = self._subscriptions.get(sid)
                if sub is not None:
                    callbacks.append(sub.callback)

        # Call callbacks OUTSIDE the lock — they may do anything (including
        # subscribe/unsubscribe), which would deadlock if we held it.
        success = 0
        for cb in callbacks:
            try:
                cb(message)
                success += 1
            except Exception:
                pass
        return success

    # ── introspection ────────────────────────────────────────────────────────

    def list_topics(self) -> list[dict]:
        with self._lock:
            names = sorted(self._topics.keys())
            return [
                {
                    "name": self._topics[n].name,
                    "subscriber_count": len(self._topic_subs.get(n, [])),
                    "created_at": self._topics[n].created_at,
                }
                for n in names
            ]

    def list_subscriptions(self, topic: str | None = None) -> list[Subscription]:
        with self._lock:
            if topic is not None:
                if topic not in self._topics:
                    return []
                sub_ids = list(self._topic_subs.get(topic, []))
                return [self._subscriptions[sid] for sid in sub_ids if sid in self._subscriptions]
            return list(self._subscriptions.values())

    def count_subscribers(self, topic: str) -> int:
        with self._lock:
            return len(self._topic_subs.get(topic, []))
