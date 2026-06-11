"""RedisBus — cross-process pub/sub via Redis Pub/Sub.

Drop-in replacement for :class:`EventBus` with an identical API::

    subscribe(topic, fn)
    unsubscribe(topic, fn)
    publish(topic, payload)

A daemon thread polls ``pubsub.get_message()`` and dispatches to local
callbacks.  Regular topics use ``SUBSCRIBE``; the wildcard ``"*"`` topic uses
``PSUBSCRIBE("*")`` so it fires for every published channel.

Select the backend at startup via environment variables::

    PRADYOS_BUS_BACKEND=redis           # activates RedisBus in get_bus()
    PRADYOS_REDIS_URL=redis://…         # connection string (default: localhost)
"""

from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

Subscriber = Callable[[str, dict[str, Any]], None]

# How long get_message() blocks per iteration.  Small enough to feel responsive
# yet large enough not to spin the CPU idle.
_POLL_TIMEOUT_S: float = 0.05


class RedisBus:
    """Cross-process pub/sub bus backed by Redis Pub/Sub.

    Parameters
    ----------
    redis_url:
        A ``redis://`` or ``rediss://`` URL.  Defaults to
        ``PRADYOS_REDIS_URL`` env-var, or ``redis://127.0.0.1:6379/0``.
    redis_client:
        Inject a pre-built redis client (e.g. ``fakeredis.FakeRedis()`` in
        tests).  When supplied, *redis_url* is ignored.
    """

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        redis_client: Any | None = None,
    ) -> None:
        # Deferred import so installations without redis-py stay importable.
        import redis as _redis  # noqa: PLC0415

        if redis_client is not None:
            self._redis = redis_client
        else:
            url = redis_url or os.environ.get("PRADYOS_REDIS_URL", "redis://127.0.0.1:6379/0")
            self._redis = _redis.from_url(url)

        self._pubsub = self._redis.pubsub()
        self._subs: dict[str, list[Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._listen,
            daemon=True,
            name="pradyos-redis-bus",
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Public API — identical to EventBus
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, fn: Subscriber) -> None:
        """Register *fn* to receive messages on *topic*.

        If *topic* is ``"*"`` the callback fires for every published message.
        """
        with self._lock:
            is_new = not self._subs[topic]
            self._subs[topic].append(fn)

        # Register with Redis outside the lock (redis-py is thread-safe).
        if is_new:
            if topic == "*":
                self._pubsub.psubscribe("*")
            else:
                self._pubsub.subscribe(topic)

    def unsubscribe(self, topic: str, fn: Subscriber) -> None:
        """Remove *fn* from *topic*.  No-op if not registered."""
        now_empty = False
        with self._lock:
            lst = self._subs.get(topic, [])
            if fn in lst:
                lst.remove(fn)
                now_empty = not lst

        if now_empty:
            if topic == "*":
                self._pubsub.punsubscribe("*")
            else:
                self._pubsub.unsubscribe(topic)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish *payload* to *topic*.  Serialised as JSON."""
        self._redis.publish(topic, json.dumps(payload))

    def stop(self) -> None:
        """Signal the receive thread to exit and wait for it.

        Intended for test teardown; production code relies on daemon=True.
        """
        self._stop.set()
        self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _listen(self) -> None:
        """Background receive loop.  Runs in a daemon thread."""
        while not self._stop.is_set():
            try:
                message = self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=_POLL_TIMEOUT_S,
                )
            except Exception:  # noqa: BLE001 — Redis transient errors
                continue

            if message is None:
                continue

            self._dispatch(message)

    def _dispatch(self, message: dict) -> None:
        """Route a raw redis-py pubsub message to local callbacks."""
        mtype = message.get("type")
        raw_channel = message.get("channel", b"")
        topic: str = raw_channel.decode() if isinstance(raw_channel, bytes) else raw_channel

        try:
            raw_data = message.get("data", b"{}")
            payload: dict = json.loads(raw_data)
        except Exception:  # noqa: BLE001 — malformed payloads are silently dropped
            payload = {}

        if mtype == "message":
            # Delivered via SUBSCRIBE — dispatch to exact-topic subscribers.
            # Wildcard subscribers receive a separate pmessage from PSUBSCRIBE.
            with self._lock:
                handlers = list(self._subs.get(topic, []))
            for fn in handlers:
                try:
                    fn(topic, payload)
                except Exception:  # noqa: BLE001 — subscriber faults are isolated
                    pass

        elif mtype == "pmessage":
            # Delivered via PSUBSCRIBE("*") — dispatch to wildcard subscribers.
            with self._lock:
                handlers = list(self._subs.get("*", []))
            for fn in handlers:
                try:
                    fn(topic, payload)
                except Exception:  # noqa: BLE001 — subscriber faults are isolated
                    pass
