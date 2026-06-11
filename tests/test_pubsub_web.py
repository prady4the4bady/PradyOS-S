"""Phase 50D — 10 tests for PubSub endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.pubsub import PubSubBroker
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_pubsub():
    return TestClient(create_app())


@pytest.fixture()
def client_with_pubsub():
    broker = PubSubBroker()
    app = create_app(pubsub=broker)
    return TestClient(app), broker


# ── GET /api/v1/pubsub/topics ─────────────────────────────────────────────────

def test_get_topics_returns_200(client_no_pubsub):
    assert client_no_pubsub.get("/api/v1/pubsub/topics").status_code == 200


def test_get_topics_no_pubsub_empty(client_no_pubsub):
    data = client_no_pubsub.get("/api/v1/pubsub/topics").json()
    assert data["topics"] == []
    assert data["count"] == 0


# ── POST /api/v1/pubsub/{topic} ───────────────────────────────────────────────

def test_publish_no_pubsub_400(client_no_pubsub):
    resp = client_no_pubsub.post("/api/v1/pubsub/x", json={"message": {"a": 1}})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_publish_missing_message_400(client_with_pubsub):
    client, _ = client_with_pubsub
    resp = client.post("/api/v1/pubsub/x", json={})
    assert resp.status_code == 400


def test_publish_returns_notified_key(client_with_pubsub):
    client, _ = client_with_pubsub
    data = client.post("/api/v1/pubsub/x", json={"message": {"v": 1}}).json()
    assert "notified" in data
    assert data["notified"] == 0  # no subscribers yet


# ── GET /api/v1/pubsub/{topic}/subscribers ────────────────────────────────────

def test_get_subscribers_returns_count_key(client_with_pubsub):
    client, _ = client_with_pubsub
    data = client.get("/api/v1/pubsub/x/subscribers").json()
    assert "subscriber_count" in data


def test_get_subscribers_no_pubsub_zero(client_no_pubsub):
    data = client_no_pubsub.get("/api/v1/pubsub/x/subscribers").json()
    assert data["subscriber_count"] == 0


# ── subscribe then publish via TestClient ────────────────────────────────────

def test_subscribe_then_publish_notified_one(client_with_pubsub):
    client, broker = client_with_pubsub
    received = []
    broker.subscribe("x", lambda m: received.append(m))
    data = client.post("/api/v1/pubsub/x", json={"message": {"v": 99}}).json()
    assert data["notified"] == 1
    assert received == [{"v": 99}]


# ── list grows after publish ──────────────────────────────────────────────────

def test_topics_list_grows_after_publish_to_new(client_with_pubsub):
    client, _ = client_with_pubsub
    client.post("/api/v1/pubsub/brand-new", json={"message": {}})
    data = client.get("/api/v1/pubsub/topics").json()
    names = [t["name"] for t in data["topics"]]
    assert "brand-new" in names


# ── subscribe count increases ─────────────────────────────────────────────────

def test_subscribe_count_increases_after_second(client_with_pubsub):
    client, broker = client_with_pubsub
    broker.subscribe("y", lambda m: None)
    assert client.get("/api/v1/pubsub/y/subscribers").json()["subscriber_count"] == 1
    broker.subscribe("y", lambda m: None)
    assert client.get("/api/v1/pubsub/y/subscribers").json()["subscriber_count"] == 2
