"""Phase 127 — tests for the /api/v1/randomprojection endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.random_projection import RandomProjection
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def rp_client():
    # Small dims for compact test vectors: 8 -> 4.
    rp = RandomProjection(input_dim=8, output_dim=4, seed=0)
    return TestClient(create_app(random_projection=rp))


# ── project ──────────────────────────────────────────────────────────────────────

def test_project_returns_output_dim(rp_client):
    resp = rp_client.post("/api/v1/randomprojection/project",
                          json={"vector": [1, 2, 3, 4, 5, 6, 7, 8]})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["projection"]) == 4 and body["output_dim"] == 4


def test_project_missing_vector_422(rp_client):
    assert rp_client.post("/api/v1/randomprojection/project", json={}).status_code == 422


def test_project_wrong_dim_422(rp_client):
    resp = rp_client.post("/api/v1/randomprojection/project", json={"vector": [1, 2, 3]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_project_non_list_422(rp_client):
    assert rp_client.post("/api/v1/randomprojection/project",
                          json={"vector": "nope"}).status_code == 422


# ── distance ─────────────────────────────────────────────────────────────────────

def test_distance(rp_client):
    body = rp_client.post("/api/v1/randomprojection/distance",
                          json={"a": [1, 2, 3, 4, 5, 6, 7, 8], "b": [8, 7, 6, 5, 4, 3, 2, 1]}).json()
    assert body["distance"] >= 0.0


def test_distance_self_zero(rp_client):
    body = rp_client.post("/api/v1/randomprojection/distance",
                          json={"a": [1, 2, 3, 4, 5, 6, 7, 8], "b": [1, 2, 3, 4, 5, 6, 7, 8]}).json()
    assert body["distance"] < 1e-9


def test_distance_missing_b_422(rp_client):
    assert rp_client.post("/api/v1/randomprojection/distance",
                          json={"a": [1, 2, 3, 4, 5, 6, 7, 8]}).status_code == 422


# ── dot ──────────────────────────────────────────────────────────────────────────

def test_dot(rp_client):
    body = rp_client.post("/api/v1/randomprojection/dot",
                          json={"a": [1, 0, 0, 0, 0, 0, 0, 0], "b": [1, 0, 0, 0, 0, 0, 0, 0]}).json()
    assert "dot" in body


def test_dot_missing_a_422(rp_client):
    assert rp_client.post("/api/v1/randomprojection/dot",
                          json={"b": [1, 2, 3, 4, 5, 6, 7, 8]}).status_code == 422


# ── stats ───────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/randomprojection/stats").json()) == {
        "input_dim", "output_dim", "compression_ratio", "seed"}


def test_stats_defaults(client):
    s = client.get("/api/v1/randomprojection/stats").json()
    assert s["input_dim"] == 128 and s["output_dim"] == 16 and s["compression_ratio"] == 8.0


# ── reset ───────────────────────────────────────────────────────────────────────

def test_reset_reconfigures(client):
    body = client.request("DELETE", "/api/v1/randomprojection/reset",
                          json={"input_dim": 64, "output_dim": 8, "seed": 9}).json()
    assert body["input_dim"] == 64 and body["output_dim"] == 8 and body["seed"] == 9


def test_reset_bad_config_422(client):
    resp = client.request("DELETE", "/api/v1/randomprojection/reset", json={"output_dim": 0})
    assert resp.status_code == 422 and "error" in resp.json()


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/randomprojection/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────

def test_project_then_reset_changes_dim(rp_client):
    rp_client.request("DELETE", "/api/v1/randomprojection/reset",
                      json={"input_dim": 4, "output_dim": 2})
    body = rp_client.post("/api/v1/randomprojection/project", json={"vector": [1, 2, 3, 4]}).json()
    assert len(body["projection"]) == 2


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries",
                  "xorfilter", "ribbon", "heavykeeper", "spectralbloom",
                  "augmentedsketch", "qdigest", "momentsketch", "countingbloom",
                  "binaryfuse", "vacuum", "stablebloom", "linearcounting", "treap",
                  "bloomier", "minhashlsh", "tinylfu", "hyperminhash", "scalablebloom",
                  "rendezvous", "maglev", "iblt", "bbitminhash", "cusketch", "jump",
                  "frugal", "simhashlsh"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
