"""Tests for RedisBus — cross-process pub/sub via Redis.

Uses ``fakeredis`` so no real Redis server is required.  Each test gets its
own ``FakeRedis`` instance via the ``bus`` fixture; the bus background thread
is cleanly stopped in teardown.

Coverage:
    - basic subscribe / publish delivery
    - multiple subscribers on the same topic
    - wildcard ``"*"`` subscription receives all topics
    - wildcard does NOT double-fire alongside a topic subscriber
    - unsubscribe stops delivery
    - subscriber exceptions are isolated (other subs still receive)
    - payloads are round-tripped as JSON dicts
    - publish() with no subscribers is a no-op (no exception)
    - get_bus() returns RedisBus when PRADYOS_BUS_BACKEND=redis
"""

from __future__ import annotations

import os
import time

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SETTLE = 0.25  # seconds — how long to wait for the background thread


def _wait(received: list, count: int = 1, timeout: float = _SETTLE) -> None:
    """Spin-wait until *received* has at least *count* items or timeout."""
    deadline = time.monotonic() + timeout
    while len(received) < count and time.monotonic() < deadline:
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_client():
    """A FakeRedis client backed by its own FakeServer (isolated per test)."""
    fakeredis = pytest.importorskip("fakeredis")
    server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server)


@pytest.fixture()
def bus(fake_client):
    """A RedisBus wired to the FakeRedis client; stopped after each test."""
    from pradyos.core.redis_bus import RedisBus
    b = RedisBus(redis_client=fake_client)
    yield b
    b.stop()


# ---------------------------------------------------------------------------
# Tests — basic pub/sub
# ---------------------------------------------------------------------------

def test_subscribe_and_publish_delivers_payload(bus):
    received = []
    bus.subscribe("task.completed", lambda t, p: received.append((t, p)))
    bus.publish("task.completed", {"agent": "titan", "ok": True})
    _wait(received)

    assert len(received) == 1
    topic, payload = received[0]
    assert topic == "task.completed"
    assert payload == {"agent": "titan", "ok": True}


def test_publish_to_unsubscribed_topic_is_noop(bus):
    received = []
    bus.subscribe("a.b", lambda t, p: received.append(p))
    bus.publish("x.y", {"data": 1})
    time.sleep(_SETTLE)

    assert received == []


def test_multiple_subscribers_on_same_topic(bus):
    hits_a: list = []
    hits_b: list = []
    bus.subscribe("incident.raised", lambda t, p: hits_a.append(p))
    bus.subscribe("incident.raised", lambda t, p: hits_b.append(p))
    bus.publish("incident.raised", {"sev": 2})
    _wait(hits_a)
    _wait(hits_b)

    assert len(hits_a) == 1
    assert len(hits_b) == 1
    assert hits_a[0] == hits_b[0] == {"sev": 2}


def test_correct_topic_isolation(bus):
    """Subscribing to 'a' must not receive messages on 'b'."""
    seen_a: list = []
    seen_b: list = []
    bus.subscribe("plane.a", lambda t, p: seen_a.append(p))
    bus.subscribe("plane.b", lambda t, p: seen_b.append(p))
    bus.publish("plane.a", {"x": 1})
    bus.publish("plane.b", {"x": 2})
    _wait(seen_a)
    _wait(seen_b)

    assert seen_a == [{"x": 1}]
    assert seen_b == [{"x": 2}]


# ---------------------------------------------------------------------------
# Tests — wildcard "*"
# ---------------------------------------------------------------------------

def test_wildcard_receives_all_topics(bus):
    """'*' subscriber fires for every published topic."""
    wild: list = []
    bus.subscribe("*", lambda t, p: wild.append(t))
    bus.publish("foo.bar", {"n": 1})
    bus.publish("baz.qux", {"n": 2})
    _wait(wild, count=2)

    assert "foo.bar" in wild
    assert "baz.qux" in wild


def test_wildcard_does_not_double_fire_alongside_topic_sub(bus):
    """A message on 'ev.x' with both a topic sub and '*' sub fires exactly
    once per subscriber, not twice for either.
    """
    topic_hits: list = []
    wild_hits: list = []
    bus.subscribe("ev.x", lambda t, p: topic_hits.append(p))
    bus.subscribe("*", lambda t, p: wild_hits.append(p))
    bus.publish("ev.x", {"v": 99})
    _wait(topic_hits)
    _wait(wild_hits)
    time.sleep(_SETTLE)  # extra wait to catch any double-fire

    assert len(topic_hits) == 1, "topic subscriber fired != 1 time"
    assert len(wild_hits) == 1, "wildcard subscriber fired != 1 time"


def test_wildcard_only_no_topic_subscriber(bus):
    """Wildcard sub with NO topic-specific sub still receives the message."""
    wild: list = []
    bus.subscribe("*", lambda t, p: wild.append((t, p)))
    bus.publish("solo.topic", {"lone": True})
    _wait(wild)

    assert wild == [("solo.topic", {"lone": True})]


# ---------------------------------------------------------------------------
# Tests — unsubscribe
# ---------------------------------------------------------------------------

def test_unsubscribe_stops_delivery(bus):
    received: list = []

    def handler(t, p):
        received.append(p)

    bus.subscribe("upd", handler)
    bus.publish("upd", {"seq": 1})
    _wait(received, count=1)
    assert len(received) == 1

    bus.unsubscribe("upd", handler)
    bus.publish("upd", {"seq": 2})
    time.sleep(_SETTLE)

    assert len(received) == 1, "handler should not fire after unsubscribe"


def test_unsubscribe_wildcard(bus):
    received: list = []

    def handler(t, p):
        received.append(p)

    bus.subscribe("*", handler)
    bus.publish("any.topic", {"a": 1})
    _wait(received, count=1)

    bus.unsubscribe("*", handler)
    bus.publish("any.topic", {"a": 2})
    time.sleep(_SETTLE)

    assert len(received) == 1, "wildcard handler should not fire after unsubscribe"


def test_unsubscribe_noop_if_not_registered(bus):
    """Unsubscribing a function that was never registered must not raise."""
    bus.unsubscribe("ghost.topic", lambda t, p: None)


# ---------------------------------------------------------------------------
# Tests — fault isolation
# ---------------------------------------------------------------------------

def test_subscriber_exception_does_not_block_other_subscribers(bus):
    """A crashing subscriber must not prevent the next one from receiving."""
    good_hits: list = []

    def bad_handler(t, p):
        raise RuntimeError("subscriber boom")

    def good_handler(t, p):
        good_hits.append(p)

    bus.subscribe("crash.test", bad_handler)
    bus.subscribe("crash.test", good_handler)
    bus.publish("crash.test", {"data": "ok"})
    _wait(good_hits)

    assert good_hits == [{"data": "ok"}]


def test_wildcard_subscriber_exception_isolated(bus):
    good: list = []

    def boom(t, p):
        raise ValueError("wildcard boom")

    def fine(t, p):
        good.append(1)

    bus.subscribe("*", boom)
    bus.subscribe("*", fine)
    bus.publish("crash.wild", {})
    _wait(good)

    assert good == [1]


# ---------------------------------------------------------------------------
# Tests — payload serialisation
# ---------------------------------------------------------------------------

def test_complex_payload_round_trips(bus):
    received: list = []
    bus.subscribe("data.event", lambda t, p: received.append(p))
    payload = {"list": [1, 2, 3], "nested": {"a": True}, "count": 42}
    bus.publish("data.event", payload)
    _wait(received)

    assert received[0] == payload


def test_empty_payload(bus):
    received: list = []
    bus.subscribe("empty", lambda t, p: received.append(p))
    bus.publish("empty", {})
    _wait(received)

    assert received[0] == {}


# ---------------------------------------------------------------------------
# Tests — get_bus() factory
# ---------------------------------------------------------------------------

def test_get_bus_returns_redis_bus_when_env_set():
    """get_bus() returns a RedisBus when PRADYOS_BUS_BACKEND=redis.

    Strategy: patch the *module-level* name ``pradyos.core.redis_bus.RedisBus``
    with a MagicMock so that ``get_bus()``'s internal
    ``from pradyos.core.redis_bus import RedisBus; RedisBus()`` picks up the
    mock without touching a real Redis server.  patch.dict ensures
    os.environ is correctly seen inside bus.get_bus().
    """
    from unittest.mock import MagicMock, patch

    import pradyos.core.bus as bus_mod
    from pradyos.core.redis_bus import RedisBus

    sentinel = MagicMock(spec=RedisBus)

    with patch.dict("os.environ", {"PRADYOS_BUS_BACKEND": "redis"}, clear=False):
        # Patch the class itself in its home module so get_bus()'s
        # `from pradyos.core.redis_bus import RedisBus` resolves to our mock.
        with patch("pradyos.core.redis_bus.RedisBus", return_value=sentinel) as MockCls:
            bus_mod._singleton = None
            try:
                b = bus_mod.get_bus()
                # The factory must have called RedisBus() exactly once.
                MockCls.assert_called_once_with()
                # The returned singleton must be what RedisBus() produced.
                assert b is sentinel
            finally:
                bus_mod._singleton = None


def test_get_bus_returns_event_bus_by_default():
    """get_bus() returns EventBus when PRADYOS_BUS_BACKEND is unset."""
    from unittest.mock import patch

    import pradyos.core.bus as bus_mod
    from pradyos.core.bus import EventBus

    # Ensure the env var is absent for this test.
    env_without_backend = {
        k: v for k, v in __import__("os").environ.items()
        if k != "PRADYOS_BUS_BACKEND"
    }
    with patch.dict("os.environ", env_without_backend, clear=True):
        bus_mod._singleton = None
        try:
            b = bus_mod.get_bus()
            assert isinstance(b, EventBus)
        finally:
            bus_mod._singleton = None
