"""Phase 61D — 10 tests for TagIndex endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.tag_index import TagIndex
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_idx():
    return TestClient(create_app())


@pytest.fixture()
def client_with_idx():
    idx = TagIndex()
    app = create_app(tag_index=idx)
    return TestClient(app), idx


# ── GET /api/v1/tags ─────────────────────────────────────────────────────────

def test_get_tags_returns_200_with_keys(client_with_idx):
    client, _ = client_with_idx
    data = client.get("/api/v1/tags").json()
    assert "tags" in data
    assert "total" in data


def test_get_no_index_empty(client_no_idx):
    data = client_no_idx.get("/api/v1/tags").json()
    assert data["tags"] == []


# ── POST /api/v1/tags/tag ────────────────────────────────────────────────────

def test_post_tag_returns_tagged_true(client_with_idx):
    client, _ = client_with_idx
    data = client.post("/api/v1/tags/tag", json={
        "item_id": "item1", "tags": ["red", "small"],
    }).json()
    assert data["tagged"] is True
    assert data["item_id"] == "item1"


# ── POST /api/v1/tags/untag ──────────────────────────────────────────────────

def test_post_untag_returns_untagged_true(client_with_idx):
    client, _ = client_with_idx
    client.post("/api/v1/tags/tag", json={
        "item_id": "item1", "tags": ["red"],
    })
    data = client.post("/api/v1/tags/untag", json={
        "item_id": "item1", "tags": ["red"],
    }).json()
    assert data["untagged"] is True


def test_post_tag_no_index_error_key(client_no_idx):
    data = client_no_idx.post("/api/v1/tags/tag", json={
        "item_id": "x", "tags": ["red"],
    }).json()
    assert "error" in data


# ── GET /api/v1/tags/items/{tag} ─────────────────────────────────────────────

def test_get_items_for_tag_returns_items(client_with_idx):
    client, _ = client_with_idx
    client.post("/api/v1/tags/tag", json={
        "item_id": "item1", "tags": ["red"],
    })
    data = client.get("/api/v1/tags/items/red").json()
    assert data["items"] == ["item1"]


def test_get_items_unknown_tag_empty(client_with_idx):
    client, _ = client_with_idx
    data = client.get("/api/v1/tags/items/phantom").json()
    assert data["items"] == []


# ── GET /api/v1/tags/search ──────────────────────────────────────────────────

def test_get_search_returns_results(client_with_idx):
    client, _ = client_with_idx
    client.post("/api/v1/tags/tag", json={
        "item_id": "a", "tags": ["red", "small"],
    })
    client.post("/api/v1/tags/tag", json={
        "item_id": "b", "tags": ["red"],
    })
    data = client.get("/api/v1/tags/search?tags=red,small&mode=all").json()
    assert data["results"] == ["a"]


# ── DELETE /api/v1/tags/items/{item_id} ──────────────────────────────────────

def test_delete_item_returns_deleted_true(client_with_idx):
    client, _ = client_with_idx
    client.post("/api/v1/tags/tag", json={
        "item_id": "item1", "tags": ["red"],
    })
    resp = client.delete("/api/v1/tags/items/item1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_second_delete_returns_404(client_with_idx):
    client, _ = client_with_idx
    client.post("/api/v1/tags/tag", json={
        "item_id": "item1", "tags": ["red"],
    })
    client.delete("/api/v1/tags/items/item1")
    resp = client.delete("/api/v1/tags/items/item1")
    assert resp.status_code == 404
