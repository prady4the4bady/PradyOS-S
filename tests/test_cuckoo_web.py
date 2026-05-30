"""Phase 86 — tests for the /api/v1/cuckoo endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.cuckoo import SovereignCuckooFilter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app SovereignCuckooFilter (cap 1024) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_det():
    # Injected hash: 'a' and 'ghost' collide (same fp + buckets) → deterministic
    # false positive once 'a' is inserted, and it clears when 'a' is deleted.
    mapping = {"a": 0x0105, "ghost": 0x0105, "z": 0x0207}

    def h(x):
        if isinstance(x, int):
            return x
        return mapping[x]

    cuckoo = SovereignCuckooFilter(capacity=4, hash_fn=h)
    return TestClient(create_app(cuckoo=cuckoo))


def _delete(client, item):
    return client.request("DELETE", "/api/v1/cuckoo/delete", json={"item": item})


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_returns_count(client):
    resp = client.post("/api/v1/cuckoo/insert", json={"item": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] is True
    assert body["count"] == 1


def test_insert_missing_item_returns_422(client):
    resp = client.post("/api/v1/cuckoo/insert", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_insert_non_dict_body_returns_422(client):
    resp = client.post("/api/v1/cuckoo/insert", json=["not", "a", "dict"])
    assert resp.status_code == 422


# ── contains ────────────────────────────────────────────────────────────────────

def test_contains_after_insert_true(client):
    client.post("/api/v1/cuckoo/insert", json={"item": "hello"})
    resp = client.post("/api/v1/cuckoo/contains", json={"item": "hello"})
    assert resp.status_code == 200
    assert resp.json()["contains"] is True


def test_contains_absent_false_deterministic(client_det):
    client_det.post("/api/v1/cuckoo/insert", json={"item": "a"})
    # 'z' maps to a distinct fingerprint AND bucket → guaranteed absent.
    assert client_det.post("/api/v1/cuckoo/contains", json={"item": "z"}).json()["contains"] is False


def test_contains_missing_item_returns_422(client):
    assert client.post("/api/v1/cuckoo/contains", json={}).status_code == 422


# ── delete ──────────────────────────────────────────────────────────────────────

def test_delete_present_returns_true(client):
    client.post("/api/v1/cuckoo/insert", json={"item": "x"})
    body = _delete(client, "x").json()
    assert body["deleted"] is True
    assert body["count"] == 0


def test_delete_absent_returns_false(client):
    body = _delete(client, "never").json()
    assert body["deleted"] is False
    assert body["count"] == 0


def test_delete_missing_item_returns_422(client):
    assert _delete(client, None) is not None  # sanity: helper builds a request
    resp = client.request("DELETE", "/api/v1/cuckoo/delete", json={})
    assert resp.status_code == 422


def test_delete_removes_membership(client_det):
    client_det.post("/api/v1/cuckoo/insert", json={"item": "a"})
    _delete(client_det, "a")
    assert client_det.post("/api/v1/cuckoo/contains", json={"item": "a"}).json()["contains"] is False


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/cuckoo/stats").json()
    assert set(data) == {"capacity", "count", "load_factor", "fingerprint_bits", "max_kicks"}


def test_stats_tracks_count(client):
    for i in range(7):
        client.post("/api/v1/cuckoo/insert", json={"item": f"k{i}"})
    assert client.get("/api/v1/cuckoo/stats").json()["count"] == 7


def test_stats_default_capacity(client):
    assert client.get("/api/v1/cuckoo/stats").json()["capacity"] == 1024


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    for i in range(20):
        client.post("/api/v1/cuckoo/insert", json={"item": f"k{i}"})
    resp = client.post("/api/v1/cuckoo/reset")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_reset_returns_stats(client):
    data = client.post("/api/v1/cuckoo/reset").json()
    assert set(data) == {"capacity", "count", "load_factor", "fingerprint_bits", "max_kicks"}


# ── deterministic membership-with-deletion over HTTP ─────────────────────────────

def test_deterministic_false_positive_and_clear_over_http(client_det):
    # 'ghost' was never inserted, but collides with 'a' → false positive…
    client_det.post("/api/v1/cuckoo/insert", json={"item": "a"})
    assert client_det.post("/api/v1/cuckoo/contains", json={"item": "ghost"}).json()["contains"] is True
    # …and deleting 'a' clears it (the Bloom filter could not do this).
    _delete(client_det, "a")
    assert client_det.post("/api/v1/cuckoo/contains", json={"item": "ghost"}).json()["contains"] is False


# ── round-trip / regression ──────────────────────────────────────────────────────

def test_insert_contains_delete_round_trip(client):
    client.post("/api/v1/cuckoo/insert", json={"item": "round"})
    assert client.post("/api/v1/cuckoo/contains", json={"item": "round"}).json()["contains"] is True
    _delete(client, "round")
    assert client.get("/api/v1/cuckoo/stats").json()["count"] == 0


def test_reinsert_after_delete_over_http(client):
    client.post("/api/v1/cuckoo/insert", json={"item": "r"})
    _delete(client, "r")
    resp = client.post("/api/v1/cuckoo/insert", json={"item": "r"})
    assert resp.json()["inserted"] is True
    assert resp.json()["count"] == 1


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83/84/85 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
    assert client.get("/api/v1/reservoir/stats").status_code == 200
