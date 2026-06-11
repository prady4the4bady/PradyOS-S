"""Phase 102 — tests for the /api/v1/heavykeeper endpoints in sovereign_web."""
from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from pradyos.core.heavykeeper import HeavyKeeper
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    # create_app() builds a fresh per-app HeavyKeeper (k=10, unbuilt) in the factory.
    return TestClient(create_app())


@pytest.fixture()
def loaded_client():
    # A pre-loaded sketch injected → topk is deterministic.
    hk = HeavyKeeper(k=10, seed=0)
    rnd = random.Random(1)
    stream = ["HEAVY"] * 1000
    for i in range(9):
        stream += [f"hot{i}"] * 100
    for j in range(2000):
        stream += [f"noise{j}"] * rnd.randint(1, 3)
    rnd.shuffle(stream)
    for x in stream:
        hk.add(x)
    return TestClient(create_app(heavykeeper=hk))


# ── add ──────────────────────────────────────────────────────────────────────────

def test_add_returns_estimate(client):
    resp = client.post("/api/v1/heavykeeper/add", json={"item": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["item"] == "x" and body["estimate"] == 1 and body["count"] == 1


def test_add_with_count(client):
    resp = client.post("/api/v1/heavykeeper/add", json={"item": "x", "count": 25})
    assert resp.json()["estimate"] == 25


def test_add_increments_across_calls(client):
    client.post("/api/v1/heavykeeper/add", json={"item": "x", "count": 10})
    resp = client.post("/api/v1/heavykeeper/add", json={"item": "x", "count": 5})
    assert resp.json()["estimate"] == 15


def test_add_missing_item_returns_422(client):
    assert client.post("/api/v1/heavykeeper/add", json={}).status_code == 422


def test_add_non_dict_body_returns_422(client):
    assert client.post("/api/v1/heavykeeper/add", json=["x"]).status_code == 422


def test_add_bad_count_returns_422(client):
    assert client.post("/api/v1/heavykeeper/add", json={"item": "x", "count": 0}).status_code == 422
    assert client.post("/api/v1/heavykeeper/add", json={"item": "x", "count": -2}).status_code == 422


# ── topk ──────────────────────────────────────────────────────────────────────────

def test_topk_empty(client):
    assert client.get("/api/v1/heavykeeper/topk").json() == {"topk": []}


def test_topk_after_adds(client):
    client.post("/api/v1/heavykeeper/add", json={"item": "big", "count": 100})
    client.post("/api/v1/heavykeeper/add", json={"item": "small", "count": 2})
    top = client.get("/api/v1/heavykeeper/topk").json()["topk"]
    assert top[0]["item"] == "big" and top[0]["count"] == 100


def test_topk_sorted_descending(client):
    for item, c in (("a", 30), ("b", 10), ("c", 20)):
        client.post("/api/v1/heavykeeper/add", json={"item": item, "count": c})
    counts = [e["count"] for e in client.get("/api/v1/heavykeeper/topk").json()["topk"]]
    assert counts == sorted(counts, reverse=True)


def test_topk_n_parameter(client):
    for i in range(8):
        client.post("/api/v1/heavykeeper/add", json={"item": f"i{i}", "count": i + 1})
    assert len(client.get("/api/v1/heavykeeper/topk", params={"n": 3}).json()["topk"]) == 3


def test_topk_bad_n_returns_422(client):
    assert client.get("/api/v1/heavykeeper/topk", params={"n": 0}).status_code == 422


def test_topk_detects_heavy_hitters(loaded_client):
    items = {e["item"] for e in loaded_client.get("/api/v1/heavykeeper/topk", params={"n": 10}).json()["topk"]}
    assert {"HEAVY"} | {f"hot{i}" for i in range(9)} <= items


def test_topk_top_item_is_heavy(loaded_client):
    top = loaded_client.get("/api/v1/heavykeeper/topk", params={"n": 1}).json()["topk"]
    assert top[0]["item"] == "HEAVY" and 800 <= top[0]["count"] <= 1200


# ── stats ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/heavykeeper/stats").json()) == {
        "k", "width", "depth", "decay", "seed", "tracked", "total"}


def test_stats_defaults(client):
    s = client.get("/api/v1/heavykeeper/stats").json()
    assert s["k"] == 10 and s["width"] == 1024 and s["depth"] == 4 and s["decay"] == 1.08


def test_stats_after_adds(client):
    client.post("/api/v1/heavykeeper/add", json={"item": "a", "count": 12})
    s = client.get("/api/v1/heavykeeper/stats").json()
    assert s["total"] == 12 and s["tracked"] == 1


# ── reset ─────────────────────────────────────────────────────────────────────────

def test_reset_clears(client):
    client.post("/api/v1/heavykeeper/add", json={"item": "a", "count": 50})
    resp = client.post("/api/v1/heavykeeper/reset", json={})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0 and resp.json()["tracked"] == 0


def test_reset_reconfigures(client):
    resp = client.post("/api/v1/heavykeeper/reset", json={"width": 2048, "decay": 1.2})
    assert resp.json()["width"] == 2048 and resp.json()["decay"] == 1.2


def test_reset_bad_config_returns_422(client):
    assert client.post("/api/v1/heavykeeper/reset", json={"decay": 1.0}).status_code == 422


# ── regression ────────────────────────────────────────────────────────────────────

def test_prior_phase_routes_still_live(client):
    for path in ("/api/v1/merkle", "/api/v1/skiplist", "/api/v1/tdigest"):
        assert client.get(path).status_code == 200
    for stats in ("cuckoo", "topk", "minhash", "quotient", "kll", "theta", "countsketch",
                  "lossycount", "ddsketch", "window", "sample", "misragries", "xorfilter", "ribbon"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
