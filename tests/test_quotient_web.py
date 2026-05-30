"""Phase 90 — tests for the /api/v1/quotient endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.quotient import QuotientFilter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app QuotientFilter (q=10 → 1024 slots).
    return TestClient(create_app())


@pytest.fixture()
def client_inj():
    # Injected hash with DISTINCT fingerprints → exact membership over HTTP.
    mapping = {f"k{i}": (5 << 8) | (i + 1) for i in range(20)}   # all quotient 5
    mapping["present"] = (3 << 8) | 1
    mapping["absent"] = (7 << 8) | 9
    qf = QuotientFilter(q=6, r=8, hash_fn=lambda x: mapping[x])
    return TestClient(create_app(quotient=qf))


def _delete(client, item):
    return client.request("DELETE", "/api/v1/quotient/delete", json={"item": item})


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_returns_count(client):
    resp = client.post("/api/v1/quotient/insert", json={"item": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] is True
    assert body["count"] == 1
    assert body["used"] == 1


def test_insert_missing_item_returns_422(client):
    resp = client.post("/api/v1/quotient/insert", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_insert_non_dict_body_returns_422(client):
    assert client.post("/api/v1/quotient/insert", json=["nope"]).status_code == 422


def test_insert_twice_counts_two(client):
    client.post("/api/v1/quotient/insert", json={"item": "dup"})
    body = client.post("/api/v1/quotient/insert", json={"item": "dup"}).json()
    assert body["count"] == 2


# ── contains ────────────────────────────────────────────────────────────────────

def test_contains_after_insert_true(client):
    client.post("/api/v1/quotient/insert", json={"item": "hello"})
    body = client.post("/api/v1/quotient/contains", json={"item": "hello"}).json()
    assert body["contains"] is True
    assert body["count"] == 1


def test_contains_absent_false_deterministic(client_inj):
    client_inj.post("/api/v1/quotient/insert", json={"item": "present"})
    body = client_inj.post("/api/v1/quotient/contains", json={"item": "absent"}).json()
    assert body["contains"] is False


def test_contains_missing_item_returns_422(client):
    assert client.post("/api/v1/quotient/contains", json={}).status_code == 422


# ── delete ──────────────────────────────────────────────────────────────────────

def test_delete_present_returns_true(client):
    client.post("/api/v1/quotient/insert", json={"item": "x"})
    body = _delete(client, "x").json()
    assert body["deleted"] is True
    assert body["used"] == 0


def test_delete_absent_returns_false(client):
    body = _delete(client, "never").json()
    assert body["deleted"] is False


def test_delete_missing_item_returns_422(client):
    resp = client.request("DELETE", "/api/v1/quotient/delete", json={})
    assert resp.status_code == 422


def test_delete_removes_membership(client):
    client.post("/api/v1/quotient/insert", json={"item": "x"})
    _delete(client, "x")
    assert client.post("/api/v1/quotient/contains", json={"item": "x"}).json()["contains"] is False


def test_delete_decrements_count(client):
    client.post("/api/v1/quotient/insert", json={"item": "d"})
    client.post("/api/v1/quotient/insert", json={"item": "d"})
    body = _delete(client, "d").json()
    assert body["count"] == 1
    assert body["deleted"] is True


# ── run-collision over HTTP (injected hash) ──────────────────────────────────────

def test_run_collision_over_http(client_inj):
    for i in range(20):
        client_inj.post("/api/v1/quotient/insert", json={"item": f"k{i}"})
    # all 20 share quotient 5 → one long run; every one must still be found
    assert all(
        client_inj.post("/api/v1/quotient/contains", json={"item": f"k{i}"}).json()["contains"]
        for i in range(20)
    )
    # delete one from the middle of the run; the rest survive
    _delete(client_inj, "k10")
    assert client_inj.post("/api/v1/quotient/contains", json={"item": "k10"}).json()["contains"] is False
    assert all(
        client_inj.post("/api/v1/quotient/contains", json={"item": f"k{i}"}).json()["contains"]
        for i in range(20) if i != 10
    )


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/quotient/stats").json()
    assert set(data) == {"q", "slots", "remainder_bits", "used", "items",
                         "load_factor", "false_positive_rate"}


def test_stats_tracks_used_and_items(client):
    client.post("/api/v1/quotient/insert", json={"item": "a"})
    client.post("/api/v1/quotient/insert", json={"item": "a"})
    client.post("/api/v1/quotient/insert", json={"item": "b"})
    data = client.get("/api/v1/quotient/stats").json()
    assert data["used"] == 2 and data["items"] == 3


def test_stats_default_slots(client):
    assert client.get("/api/v1/quotient/stats").json()["slots"] == 1024


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    for i in range(20):
        client.post("/api/v1/quotient/insert", json={"item": f"k{i}"})
    resp = client.post("/api/v1/quotient/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["used"] == 0 and resp.json()["items"] == 0


def test_reset_reconfigures(client):
    resp = client.post("/api/v1/quotient/reset", json={"q": 6, "r": 12})
    assert resp.json()["slots"] == 64 and resp.json()["remainder_bits"] == 12


def test_reset_bad_config_returns_422(client):
    assert client.post("/api/v1/quotient/reset", json={"q": 0}).status_code == 422


# ── round-trip / regression ───────────────────────────────────────────────────────

def test_insert_contains_delete_round_trip(client):
    client.post("/api/v1/quotient/insert", json={"item": "round"})
    assert client.post("/api/v1/quotient/contains", json={"item": "round"}).json()["contains"] is True
    _delete(client, "round")
    assert client.get("/api/v1/quotient/stats").json()["used"] == 0


def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest",
                 "/api/v1/fenwick", "/api/v1/segtree", "/api/v1/unionfind"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "error" in resp.json()
    # Phase 83–89 routes still respond
    assert client.get("/api/v1/trie/anykey").status_code == 404
    assert client.get("/api/v1/lru/snapshot").status_code == 200
    assert client.get("/api/v1/reservoir/stats").status_code == 200
    assert client.get("/api/v1/cuckoo/stats").status_code == 200
    assert client.get("/api/v1/topk/stats").status_code == 200
    assert client.get("/api/v1/minhash/stats").status_code == 200
    assert client.get("/api/v1/simhash/stats").status_code == 200
