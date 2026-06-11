"""Phase 114 — tests for the /api/v1/bloomier endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.bloomier import BloomierFilter
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    bf = BloomierFilter(seed=0)
    bf.build({f"member-{i}": f"value-{i}" for i in range(1000)})
    return TestClient(create_app(bloomier=bf))


# ── build ──────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    resp = client.post("/api/v1/bloomier/build", json={"mapping": {"a": 1, "b": 2, "c": 3}})
    assert resp.status_code == 200
    assert resp.json()["built"] is True and resp.json()["num_keys"] == 3


def test_build_missing_mapping_422(client):
    assert client.post("/api/v1/bloomier/build", json={}).status_code == 422


def test_build_mapping_not_object_422(client):
    assert client.post("/api/v1/bloomier/build", json={"mapping": "nope"}).status_code == 422


def test_build_empty_mapping_ok(client):
    resp = client.post("/api/v1/bloomier/build", json={"mapping": {}})
    assert resp.status_code == 200 and resp.json()["built"] is True and resp.json()["num_keys"] == 0


def test_build_rebuild_replaces(client):
    client.post("/api/v1/bloomier/build", json={"mapping": {"first": 1}})
    client.post("/api/v1/bloomier/build", json={"mapping": {"second": 2}})
    assert client.get("/api/v1/bloomier/get", params={"key": "second"}).json()["value"] == 2
    assert client.get("/api/v1/bloomier/get", params={"key": "first"}).json()["found"] is False


# ── get ──────────────────────────────────────────────────────────────────────────

def test_get_member_exact(loaded_client):
    body = loaded_client.get("/api/v1/bloomier/get", params={"key": "member-42"}).json()
    assert body["found"] is True and body["value"] == "value-42"


def test_get_all_members_exact(loaded_client):
    assert all(
        loaded_client.get("/api/v1/bloomier/get", params={"key": f"member-{i}"}).json()["value"]
        == f"value-{i}" for i in range(0, 1000, 25))


def test_get_non_member(loaded_client):
    body = loaded_client.get("/api/v1/bloomier/get", params={"key": "ghost-zzz"}).json()
    assert body["found"] is False and body["value"] is None


def test_get_before_build_returns_400(client):
    resp = client.get("/api/v1/bloomier/get", params={"key": "x"})
    assert resp.status_code == 400 and "not built" in resp.json()["error"]


def test_get_missing_param_422(client):
    client.post("/api/v1/bloomier/build", json={"mapping": {"a": 1}})
    assert client.get("/api/v1/bloomier/get").status_code == 422


def test_get_value_types(client):
    client.post("/api/v1/bloomier/build",
                json={"mapping": {"n": 42, "s": "txt", "list": [1, 2], "obj": {"k": 1}}})
    assert client.get("/api/v1/bloomier/get", params={"key": "list"}).json()["value"] == [1, 2]
    assert client.get("/api/v1/bloomier/get", params={"key": "obj"}).json()["value"] == {"k": 1}


def test_fp_rate_bounded(loaded_client):
    fp = sum(1 for i in range(2000)
             if loaded_client.get("/api/v1/bloomier/get",
                                  params={"key": f"nonmember-{i}"}).json()["found"])
    assert fp / 2000 < 0.02


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/bloomier/stats").json()) == {
        "built", "num_keys", "num_cells", "fingerprint_bits", "value_bits",
        "bits_per_key", "seed"}


def test_stats_unbuilt(client):
    s = client.get("/api/v1/bloomier/stats").json()
    assert s["built"] is False and s["num_keys"] == 0 and s["bits_per_key"] is None


def test_stats_after_build(loaded_client):
    s = loaded_client.get("/api/v1/bloomier/stats").json()
    assert s["built"] is True and s["num_keys"] == 1000 and s["bits_per_key"] is not None


# ── reset (DELETE with body) ──────────────────────────────────────────────────────

def test_reset_clears(loaded_client):
    resp = loaded_client.request("DELETE", "/api/v1/bloomier/reset", json={})
    assert resp.status_code == 200 and resp.json()["built"] is False


def test_reset_then_get_400(loaded_client):
    loaded_client.request("DELETE", "/api/v1/bloomier/reset", json={})
    assert loaded_client.get("/api/v1/bloomier/get", params={"key": "member-0"}).status_code == 400


def test_reset_reconfigures_seed(client):
    assert client.request("DELETE", "/api/v1/bloomier/reset", json={"seed": 5}).json()["seed"] == 5


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/bloomier/reset").status_code == 200


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
