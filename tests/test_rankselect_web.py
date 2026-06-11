"""Phase 134 — tests for the /api/v1/rankselect endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.rank_select import RankSelect
from pradyos.sovereign_web import create_app


# Known vector "1101001101": ones at 0,1,3,6,7,9 (count1=6); zeros at 2,4,5,8 (count0=4).
BITS = "1101001101"


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    return TestClient(create_app(rank_select=RankSelect(BITS)))


# ── build ──────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/rankselect/build", json={"bits": BITS}).json()
    assert body["size"] == 10 and body["count1"] == 6 and body["count0"] == 4


def test_build_missing_bits_422(client):
    assert client.post("/api/v1/rankselect/build", json={}).status_code == 422


def test_build_bad_bits_422(client):
    resp = client.post("/api/v1/rankselect/build", json={"bits": "012"})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_list_bits(client):
    body = client.post("/api/v1/rankselect/build", json={"bits": [1, 0, 1, 1]}).json()
    assert body["count1"] == 3 and body["size"] == 4


# ── rank ─────────────────────────────────────────────────────────────────────────────────

def test_rank1(built_client):
    body = built_client.get("/api/v1/rankselect/rank", params={"i": 4}).json()
    assert body["rank"] == 3 and body["bit"] == 1            # ones in [0,4) = {0,1,3}


def test_rank0(built_client):
    body = built_client.get("/api/v1/rankselect/rank", params={"i": 4, "bit": 0}).json()
    assert body["rank"] == 1                                 # zeros in [0,4) = {2}


def test_rank_full(built_client):
    assert built_client.get("/api/v1/rankselect/rank", params={"i": 10}).json()["rank"] == 6


def test_rank_missing_i_422(built_client):
    assert built_client.get("/api/v1/rankselect/rank").status_code == 422


def test_rank_negative_i_422(built_client):
    assert built_client.get("/api/v1/rankselect/rank", params={"i": -1}).status_code == 422


def test_rank_over_n_422(built_client):
    resp = built_client.get("/api/v1/rankselect/rank", params={"i": 11})
    assert resp.status_code == 422 and "error" in resp.json()


# ── select ───────────────────────────────────────────────────────────────────────────────

def test_select1(built_client):
    body = built_client.get("/api/v1/rankselect/select", params={"k": 3}).json()
    assert body["position"] == 3 and body["bit"] == 1        # 3rd set bit is at index 3


def test_select0(built_client):
    body = built_client.get("/api/v1/rankselect/select", params={"k": 2, "bit": 0}).json()
    assert body["position"] == 4                             # 2nd clear bit is at index 4


def test_select_missing_k_422(built_client):
    assert built_client.get("/api/v1/rankselect/select").status_code == 422


def test_select_k_zero_422(built_client):
    assert built_client.get("/api/v1/rankselect/select", params={"k": 0}).status_code == 422


def test_select_overcount_422(built_client):
    resp = built_client.get("/api/v1/rankselect/select", params={"k": 7})   # only 6 ones
    assert resp.status_code == 422 and "error" in resp.json()


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/rankselect/stats").json()) == {
        "size", "count1", "count0", "num_words", "num_superblocks"}


def test_stats_defaults(client):
    s = client.get("/api/v1/rankselect/stats").json()
    assert s["size"] == 0 and s["count1"] == 0


def test_stats_built(built_client):
    s = built_client.get("/api/v1/rankselect/stats").json()
    assert s["size"] == 10 and s["count1"] == 6 and s["count0"] == 4


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    body = built_client.request("DELETE", "/api/v1/rankselect/reset").json()
    assert body["size"] == 0 and body["count1"] == 0


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/rankselect/reset").status_code == 200


# ── round-trip ────────────────────────────────────────────────────────────────────────

def test_rank_select_roundtrip(built_client):
    # select1(k) then rank1(pos+1) == k for every k.
    for k in range(1, 7):
        pos = built_client.get("/api/v1/rankselect/select", params={"k": k}).json()["position"]
        assert built_client.get("/api/v1/rankselect/rank", params={"i": pos + 1}).json()["rank"] == k


def test_build_then_query_large(client):
    bits = "".join("1" if i % 3 == 0 else "0" for i in range(600))
    client.post("/api/v1/rankselect/build", json={"bits": bits})
    assert client.get("/api/v1/rankselect/select", params={"k": 1}).json()["position"] == 0
    assert client.get("/api/v1/rankselect/stats").json()["count1"] == 200


# ── regression ────────────────────────────────────────────────────────────────────────

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
                  "frugal", "simhashlsh", "randomprojection", "gcs", "fmsketch", "ams",
                  "prioritysample", "cuckoohash", "splaytree"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
