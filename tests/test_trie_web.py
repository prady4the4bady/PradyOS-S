"""Phase 83 — tests for the /api/v1/trie endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.trie import SovereignTrie
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app SovereignTrie inside the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_seeded():
    trie = SovereignTrie()
    for word in ("car", "card", "cat", "dog"):
        trie.insert(word, word.upper())
    return TestClient(create_app(trie=trie))


# ── insert ────────────────────────────────────────────────────────────────────

def test_insert_returns_key_value_size(client):
    resp = client.post("/api/v1/trie", json={"key": "cat", "value": 42})
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] == "cat"
    assert body["value"] == 42
    assert body["size"] == 1


def test_insert_default_value(client):
    resp = client.post("/api/v1/trie", json={"key": "k"})
    assert resp.json()["value"] is True


def test_insert_missing_key_returns_422(client):
    resp = client.post("/api/v1/trie", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_insert_empty_key_returns_422(client):
    assert client.post("/api/v1/trie", json={"key": ""}).status_code == 422


# ── search ────────────────────────────────────────────────────────────────────

def test_search_found(client):
    client.post("/api/v1/trie", json={"key": "cat", "value": 7})
    body = client.get("/api/v1/trie/cat").json()
    assert body["found"] is True
    assert body["value"] == 7


def test_search_absent_returns_404(client):
    resp = client.get("/api/v1/trie/ghost")
    assert resp.status_code == 404
    assert resp.json()["found"] is False


def test_search_prefix_is_not_a_key(client):
    client.post("/api/v1/trie", json={"key": "cat"})
    assert client.get("/api/v1/trie/ca").status_code == 404


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_existing(client):
    client.post("/api/v1/trie", json={"key": "cat"})
    resp = client.delete("/api/v1/trie/cat")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert client.get("/api/v1/trie/cat").status_code == 404


def test_delete_absent_returns_404(client):
    resp = client.delete("/api/v1/trie/ghost")
    assert resp.status_code == 404
    assert resp.json()["deleted"] is False


# ── prefix scan ───────────────────────────────────────────────────────────────

def test_prefix_returns_sorted_matches(client_seeded):
    body = client_seeded.get("/api/v1/trie/prefix/ca").json()
    assert body["prefix"] == "ca"
    assert body["count"] == 3
    assert [m[0] for m in body["matches"]] == ["car", "card", "cat"]


def test_prefix_absent_returns_empty(client_seeded):
    body = client_seeded.get("/api/v1/trie/prefix/zzz").json()
    assert body["matches"] == []
    assert body["count"] == 0


def test_prefix_includes_values(client_seeded):
    body = client_seeded.get("/api/v1/trie/prefix/dog").json()
    assert body["matches"] == [["dog", "DOG"]]


# ── round-trip / injected ─────────────────────────────────────────────────────

def test_insert_search_delete_round_trip(client):
    client.post("/api/v1/trie", json={"key": "alpha", "value": 1})
    assert client.get("/api/v1/trie/alpha").json()["value"] == 1
    client.delete("/api/v1/trie/alpha")
    assert client.get("/api/v1/trie/alpha").status_code == 404


def test_injected_trie_is_used(client_seeded):
    assert client_seeded.get("/api/v1/trie/card").json()["value"] == "CARD"


# ── regression: prior phases' routes still live ───────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
