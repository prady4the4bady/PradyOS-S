"""Phase 109 — tests for the /api/v1/vacuum endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.vacuum_filter import VacuumFilter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app VacuumFilter (cap 1024) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def client_det():
    # Injected hash: 'a' and 'ghost' collide (same fp + buckets) → deterministic
    # false positive once 'a' is inserted, and it clears when 'a' is deleted.
    mapping = {"a": 0x0105, "ghost": 0x0105, "z": 0x9207}

    def h(x):
        if isinstance(x, int):
            return x
        return mapping[x]

    vf = VacuumFilter(capacity=64, hash_fn=h)
    return TestClient(create_app(vacuum_filter=vf))


def _delete(client, item):
    return client.request("DELETE", "/api/v1/vacuum/delete", json={"item": item})


# ── insert ──────────────────────────────────────────────────────────────────────

def test_insert_returns_count(client):
    resp = client.post("/api/v1/vacuum/insert", json={"item": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] is True
    assert body["count"] == 1


def test_insert_missing_item_returns_422(client):
    resp = client.post("/api/v1/vacuum/insert", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_insert_non_dict_body_returns_422(client):
    resp = client.post("/api/v1/vacuum/insert", json=["not", "a", "dict"])
    assert resp.status_code == 422


# ── contains ────────────────────────────────────────────────────────────────────

def test_contains_after_insert_true(client):
    client.post("/api/v1/vacuum/insert", json={"item": "hello"})
    resp = client.post("/api/v1/vacuum/contains", json={"item": "hello"})
    assert resp.status_code == 200
    assert resp.json()["contains"] is True


def test_contains_absent_false_deterministic(client_det):
    client_det.post("/api/v1/vacuum/insert", json={"item": "a"})
    # 'z' maps to a distinct fingerprint AND chunk → guaranteed absent.
    assert client_det.post("/api/v1/vacuum/contains", json={"item": "z"}).json()["contains"] is False


def test_contains_missing_item_returns_422(client):
    assert client.post("/api/v1/vacuum/contains", json={}).status_code == 422


# ── delete ──────────────────────────────────────────────────────────────────────

def test_delete_present_returns_true(client):
    client.post("/api/v1/vacuum/insert", json={"item": "x"})
    body = _delete(client, "x").json()
    assert body["deleted"] is True
    assert body["count"] == 0


def test_delete_absent_returns_false(client):
    body = _delete(client, "never").json()
    assert body["deleted"] is False
    assert body["count"] == 0


def test_delete_missing_item_returns_422(client):
    resp = client.request("DELETE", "/api/v1/vacuum/delete", json={})
    assert resp.status_code == 422


def test_delete_removes_membership(client_det):
    client_det.post("/api/v1/vacuum/insert", json={"item": "a"})
    _delete(client_det, "a")
    assert client_det.post("/api/v1/vacuum/contains", json={"item": "a"}).json()["contains"] is False


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    data = client.get("/api/v1/vacuum/stats").json()
    assert set(data) == {"capacity", "num_chunks", "alt_range", "count",
                         "load_factor", "fingerprint_bits", "max_kicks"}


def test_stats_tracks_count(client):
    for i in range(7):
        client.post("/api/v1/vacuum/insert", json={"item": f"k{i}"})
    assert client.get("/api/v1/vacuum/stats").json()["count"] == 7


def test_stats_default_capacity_is_multiple_of_range(client):
    s = client.get("/api/v1/vacuum/stats").json()
    assert s["capacity"] == 1024
    assert s["capacity"] % s["alt_range"] == 0
    assert s["capacity"] == s["num_chunks"] * s["alt_range"]


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    for i in range(20):
        client.post("/api/v1/vacuum/insert", json={"item": f"k{i}"})
    resp = client.post("/api/v1/vacuum/reset")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_reset_returns_stats(client):
    data = client.post("/api/v1/vacuum/reset").json()
    assert set(data) == {"capacity", "num_chunks", "alt_range", "count",
                         "load_factor", "fingerprint_bits", "max_kicks"}


# ── deterministic membership-with-deletion over HTTP ─────────────────────────────

def test_deterministic_false_positive_and_clear_over_http(client_det):
    # 'ghost' was never inserted, but collides with 'a' → false positive…
    client_det.post("/api/v1/vacuum/insert", json={"item": "a"})
    assert client_det.post("/api/v1/vacuum/contains", json={"item": "ghost"}).json()["contains"] is True
    # …and deleting 'a' clears it (the Bloom filter could not do this).
    _delete(client_det, "a")
    assert client_det.post("/api/v1/vacuum/contains", json={"item": "ghost"}).json()["contains"] is False


# ── round-trip / no false negatives over HTTP ────────────────────────────────────

def test_insert_contains_delete_round_trip(client):
    client.post("/api/v1/vacuum/insert", json={"item": "round"})
    assert client.post("/api/v1/vacuum/contains", json={"item": "round"}).json()["contains"] is True
    _delete(client, "round")
    assert client.get("/api/v1/vacuum/stats").json()["count"] == 0


def test_reinsert_after_delete_over_http(client):
    client.post("/api/v1/vacuum/insert", json={"item": "r"})
    _delete(client, "r")
    resp = client.post("/api/v1/vacuum/insert", json={"item": "r"})
    assert resp.json()["inserted"] is True
    assert resp.json()["count"] == 1


def test_no_false_negatives_over_http(client):
    for i in range(0, 400):
        client.post("/api/v1/vacuum/insert", json={"item": f"m-{i}"})
    assert all(
        client.post("/api/v1/vacuum/contains", json={"item": f"m-{i}"}).json()["contains"]
        for i in range(0, 400, 7))


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
