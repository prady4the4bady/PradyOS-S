"""Phase 108 — tests for the /api/v1/binaryfuse endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.binary_fuse import BinaryFuseFilter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    bf = BinaryFuseFilter(seed=0)
    bf.build([f"member-{i}" for i in range(1000)])
    return TestClient(create_app(binary_fuse=bf))


# ── build ──────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    resp = client.post("/api/v1/binaryfuse/build", json={"keys": ["a", "b", "c"]})
    assert resp.status_code == 200
    assert resp.json()["built"] is True and resp.json()["num_keys"] == 3


def test_build_missing_keys_returns_422(client):
    assert client.post("/api/v1/binaryfuse/build", json={}).status_code == 422


def test_build_keys_not_list_returns_422(client):
    assert client.post("/api/v1/binaryfuse/build", json={"keys": "abc"}).status_code == 422


def test_build_duplicate_keys_returns_400(client):
    resp = client.post("/api/v1/binaryfuse/build", json={"keys": ["x", "x", "y"]})
    assert resp.status_code == 400 and "duplicate" in resp.json()["error"]


def test_build_empty_keys_ok(client):
    resp = client.post("/api/v1/binaryfuse/build", json={"keys": []})
    assert resp.status_code == 200 and resp.json()["built"] is True


def test_build_rebuild_replaces(client):
    client.post("/api/v1/binaryfuse/build", json={"keys": ["first"]})
    client.post("/api/v1/binaryfuse/build", json={"keys": ["second"]})
    assert client.get("/api/v1/binaryfuse/contains", params={"key": "second"}).json()["contains"]
    assert not client.get("/api/v1/binaryfuse/contains", params={"key": "first"}).json()["contains"]


# ── contains ───────────────────────────────────────────────────────────────────────

def test_contains_member(client):
    client.post("/api/v1/binaryfuse/build", json={"keys": ["apple", "banana"]})
    body = client.get("/api/v1/binaryfuse/contains", params={"key": "apple"}).json()
    assert body["key"] == "apple" and body["contains"] is True


def test_contains_nonmember(client):
    client.post("/api/v1/binaryfuse/build", json={"keys": ["apple"]})
    assert client.get("/api/v1/binaryfuse/contains", params={"key": "zzz-ghost"}).json()["contains"] is False


def test_contains_before_build_returns_400(client):
    resp = client.get("/api/v1/binaryfuse/contains", params={"key": "x"})
    assert resp.status_code == 400 and "not built" in resp.json()["error"]


def test_contains_missing_param_returns_422(client):
    client.post("/api/v1/binaryfuse/build", json={"keys": ["a"]})
    assert client.get("/api/v1/binaryfuse/contains").status_code == 422


def test_no_false_negatives(loaded_client):
    assert all(
        loaded_client.get("/api/v1/binaryfuse/contains", params={"key": f"member-{i}"}).json()["contains"]
        for i in range(0, 1000, 25))


def test_fpr_within_bound(loaded_client):
    fp = sum(
        1 for i in range(5000)
        if loaded_client.get("/api/v1/binaryfuse/contains", params={"key": f"nonmember-{i}"}).json()["contains"])
    assert fp / 5000 <= 0.01


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/binaryfuse/stats").json()) == {
        "built", "num_keys", "array_size", "bits_per_key", "seed"}


def test_stats_unbuilt(client):
    s = client.get("/api/v1/binaryfuse/stats").json()
    assert s["built"] is False and s["num_keys"] == 0 and s["bits_per_key"] is None


def test_stats_after_build(loaded_client):
    s = loaded_client.get("/api/v1/binaryfuse/stats").json()
    assert s["built"] is True and s["num_keys"] == 1000 and s["bits_per_key"] <= 10.0


# ── reset (DELETE with body) ────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/binaryfuse/build", json={"keys": ["a", "b"]})
    resp = client.request("DELETE", "/api/v1/binaryfuse/reset", json={})
    assert resp.status_code == 200 and resp.json()["built"] is False


def test_reset_then_contains_returns_400(client):
    client.post("/api/v1/binaryfuse/build", json={"keys": ["a"]})
    client.request("DELETE", "/api/v1/binaryfuse/reset", json={})
    assert client.get("/api/v1/binaryfuse/contains", params={"key": "a"}).status_code == 400


def test_reset_reconfigures_seed(client):
    resp = client.request("DELETE", "/api/v1/binaryfuse/reset", json={"seed": 5})
    assert resp.json()["seed"] == 5


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/binaryfuse/reset").status_code == 200


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
