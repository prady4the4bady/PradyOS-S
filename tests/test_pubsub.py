"""Phase 50C — 20 tests for pradyos.core.pubsub.PubSubBroker."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.pubsub import PubSubBroker, Subscription, Topic


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty():
    b = PubSubBroker()
    assert b._topics == {}
    assert b._subscriptions == {}
    assert b._topic_subs == {}


# ── subscribe ─────────────────────────────────────────────────────────────────

def test_subscribe_returns_subscription():
    b = PubSubBroker()
    sub = b.subscribe("topic.a", lambda msg: None)
    assert isinstance(sub, Subscription)
    assert sub.topic == "topic.a"


def test_subscribe_auto_creates_topic():
    b = PubSubBroker()
    b.subscribe("new.topic", lambda msg: None)
    assert "new.topic" in b._topics
    assert isinstance(b._topics["new.topic"], Topic)


def test_subscribe_assigns_uuid_hex_id():
    b = PubSubBroker()
    sub = b.subscribe("t", lambda msg: None)
    assert isinstance(sub.id, str)
    int(sub.id, 16)


def test_subscribe_second_returns_different_id():
    b = PubSubBroker()
    s1 = b.subscribe("t", lambda msg: None)
    s2 = b.subscribe("t", lambda msg: None)
    assert s1.id != s2.id


# ── unsubscribe ──────────────────────────────────────────────────────────────

def test_unsubscribe_returns_true_known():
    b = PubSubBroker()
    sub = b.subscribe("t", lambda msg: None)
    assert b.unsubscribe(sub.id) is True


def test_unsubscribe_returns_false_unknown():
    b = PubSubBroker()
    assert b.unsubscribe("phantom") is False


def test_unsubscribe_removes_from_list():
    b = PubSubBroker()
    sub = b.subscribe("t", lambda msg: None)
    b.unsubscribe(sub.id)
    assert b.list_subscriptions("t") == []


# ── publish ───────────────────────────────────────────────────────────────────

def test_publish_calls_callback_with_message():
    b = PubSubBroker()
    received: list[dict] = []
    b.subscribe("t", lambda msg: received.append(msg))
    b.publish("t", {"v": 42})
    assert received == [{"v": 42}]


def test_publish_returns_success_count():
    b = PubSubBroker()
    b.subscribe("t", lambda msg: None)
    b.subscribe("t", lambda msg: None)
    assert b.publish("t", {}) == 2


def test_publish_swallows_exceptions_and_continues():
    b = PubSubBroker()
    good_calls = []

    def bad(msg):
        raise RuntimeError("boom")

    def good(msg):
        good_calls.append(msg)

    b.subscribe("t", bad)
    b.subscribe("t", good)
    notified = b.publish("t", {"x": 1})
    assert notified == 1  # only `good` succeeded
    assert good_calls == [{"x": 1}]


def test_publish_zero_subscribers_returns_zero():
    b = PubSubBroker()
    assert b.publish("nobody", {}) == 0


def test_publish_auto_creates_topic():
    b = PubSubBroker()
    b.publish("fresh", {})
    assert "fresh" in b._topics


# ── list_topics ──────────────────────────────────────────────────────────────

def test_list_topics_sorted():
    b = PubSubBroker()
    b.subscribe("zzz", lambda m: None)
    b.subscribe("aaa", lambda m: None)
    b.subscribe("mmm", lambda m: None)
    names = [t["name"] for t in b.list_topics()]
    assert names == ["aaa", "mmm", "zzz"]


def test_list_topics_entry_has_required_keys():
    b = PubSubBroker()
    b.subscribe("t", lambda m: None)
    entry = b.list_topics()[0]
    for k in ("name", "subscriber_count", "created_at"):
        assert k in entry


def test_list_topics_subscriber_count_decrements_after_unsubscribe():
    b = PubSubBroker()
    s1 = b.subscribe("t", lambda m: None)
    b.subscribe("t", lambda m: None)
    assert b.list_topics()[0]["subscriber_count"] == 2
    b.unsubscribe(s1.id)
    assert b.list_topics()[0]["subscriber_count"] == 1


# ── list_subscriptions ───────────────────────────────────────────────────────

def test_list_subscriptions_returns_all_when_no_topic():
    b = PubSubBroker()
    b.subscribe("t1", lambda m: None)
    b.subscribe("t2", lambda m: None)
    assert len(b.list_subscriptions()) == 2


def test_list_subscriptions_filtered_by_topic():
    b = PubSubBroker()
    b.subscribe("t1", lambda m: None)
    b.subscribe("t2", lambda m: None)
    b.subscribe("t1", lambda m: None)
    assert len(b.list_subscriptions("t1")) == 2
    assert len(b.list_subscriptions("t2")) == 1


# ── count_subscribers ────────────────────────────────────────────────────────

def test_count_subscribers_correct():
    b = PubSubBroker()
    b.subscribe("t", lambda m: None)
    b.subscribe("t", lambda m: None)
    b.subscribe("t", lambda m: None)
    assert b.count_subscribers("t") == 3
    assert b.count_subscribers("nope") == 0


# ── thread safety ────────────────────────────────────────────────────────────

def test_thread_safety_50_concurrent_subscribes():
    b = PubSubBroker()
    errors: list[Exception] = []

    def worker(i: int):
        try:
            b.subscribe("hot", lambda m: None)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert b.count_subscribers("hot") == 50
