"""Phase 104 — tests for the /api/v1/augmentedsketch endpoints in sovereign_web."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.augmented_sketch import AugmentedSketch
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    a = AugmentedSketch(k=10, seed=0)
    rnd = random.Random(1)
    stream = ["HEAVY"] * 1000
    for i in range(4):
        stream += [f"hot{i}"] * 100
    for j in range(2000):
        stream += [f"noise{j}"] * rnd.randint(1, 3)
    rnd.shuffle(stream)
    for x in stream:
        a.add(x)
    return TestClient(create_app(augmented_sketch=a))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_estimate(client):
    resp = client.post("/api/v1/augmentedsketch/add", json={"item": "x"})
    assert resp.status_code == 200
    assert resp.json()["item"] == "x" and resp.json()["estimate"] == 1


def test_add_with_delta(client):
    assert client.post("/api/v1/augmentedsketch/add", json={"item": "x", "delta": 25}).json()["estimate"] == 25


def test_add_accumulates(client):
    client.post("/api/v1/augmentedsketch/add", json={"item": "x", "delta": 3})
    assert client.post("/api/v1/augmentedsketch/add", json={"item": "x", "delta": 4}).json()["estimate"] == 7


def test_add_missing_item_returns_422(client):
    assert client.post("/api/v1/augmentedsketch/add", json={}).status_code == 422


def test_add_non_dict_body_returns_422(client):
    assert client.post("/api/v1/augmentedsketch/add", json=["x"]).status_code == 422


def test_add_bad_delta_returns_422(client):
    assert client.post("/api/v1/augmentedsketch/add", json={"item": "x", "delta": 0}).status_code == 422


# ── query ─────────────────────────────────────────────────────────────────────────

def test_query_tracked_item(client):
    client.post("/api/v1/augmentedsketch/add", json={"item": "k", "delta": 40})
    body = client.get("/api/v1/augmentedsketch/query", params={"item": "k"}).json()
    assert body["item"] == "k" and body["count"] == 40


def test_query_absent_is_zero(client):
    assert client.get("/api/v1/augmentedsketch/query", params={"item": "ghost"}).json()["count"] == 0


def test_query_missing_param_returns_422(client):
    assert client.get("/api/v1/augmentedsketch/query").status_code == 422


# ── topk ──────────────────────────────────────────────────────────────────────────

def test_topk_empty(client):
    assert client.get("/api/v1/augmentedsketch/topk").json() == {"topk": []}


def test_topk_after_adds(client):
    client.post("/api/v1/augmentedsketch/add", json={"item": "big", "delta": 100})
    client.post("/api/v1/augmentedsketch/add", json={"item": "small", "delta": 2})
    top = client.get("/api/v1/augmentedsketch/topk").json()["topk"]
    assert top[0]["item"] == "big" and top[0]["count"] == 100


def test_topk_sorted_descending(client):
    for item, d in (("a", 30), ("b", 10), ("c", 20)):
        client.post("/api/v1/augmentedsketch/add", json={"item": item, "delta": d})
    counts = [e["count"] for e in client.get("/api/v1/augmentedsketch/topk").json()["topk"]]
    assert counts == sorted(counts, reverse=True)


def test_topk_n_parameter(client):
    for i in range(8):
        client.post("/api/v1/augmentedsketch/add", json={"item": f"i{i}", "delta": i + 1})
    assert len(client.get("/api/v1/augmentedsketch/topk", params={"n": 3}).json()["topk"]) == 3


def test_topk_bad_n_returns_422(client):
    assert client.get("/api/v1/augmentedsketch/topk", params={"n": 0}).status_code == 422


def test_topk_detects_heavy_hitters(loaded_client):
    items = {e["item"] for e in loaded_client.get("/api/v1/augmentedsketch/topk", params={"n": 10}).json()["topk"]}
    assert ({"HEAVY"} | {f"hot{i}" for i in range(4)}) <= items


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/augmentedsketch/stats").json()) == {
        "width", "depth", "k", "seed", "tracked", "total"}


def test_stats_defaults(client):
    s = client.get("/api/v1/augmentedsketch/stats").json()
    assert s["width"] == 1024 and s["depth"] == 4 and s["k"] == 10


def test_stats_after_adds(client):
    client.post("/api/v1/augmentedsketch/add", json={"item": "a", "delta": 12})
    s = client.get("/api/v1/augmentedsketch/stats").json()
    assert s["total"] == 12 and s["tracked"] == 1


# ── reset ─────────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/augmentedsketch/add", json={"item": "a", "delta": 50})
    resp = client.post("/api/v1/augmentedsketch/reset", json={})
    assert resp.status_code == 200 and resp.json()["total"] == 0 and resp.json()["tracked"] == 0


def test_reset_reconfigures(client):
    resp = client.post("/api/v1/augmentedsketch/reset", json={"width": 2048, "k": 5})
    assert resp.json()["width"] == 2048 and resp.json()["k"] == 5


def test_reset_bad_config_returns_422(client):
    assert client.post("/api/v1/augmentedsketch/reset", json={"width": 0}).status_code == 422


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "minhash", "quotient", "kll", "theta", "countsketch", "lossycount",
                  "ddsketch", "window", "sample", "misragries", "xorfilter", "ribbon",
                  "heavykeeper", "spectralbloom"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
