"""Phase 135 — tests for the /api/v1/wavelet endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.wavelet_tree import WaveletTree
from pradyos.sovereign_web import create_app


# Known sequence [3,1,4,1,5]: alphabet {1,3,4,5}; ones at positions 1,3.
SEQ = [3, 1, 4, 1, 5]


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def built_client():
    return TestClient(create_app(wavelet_tree=WaveletTree(SEQ)))


# ── build ──────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/wavelet/build", json={"sequence": SEQ}).json()
    assert body["size"] == 5 and body["alphabet_size"] == 4


def test_build_missing_sequence_422(client):
    assert client.post("/api/v1/wavelet/build", json={}).status_code == 422


def test_build_mixed_kind_422(client):
    resp = client.post("/api/v1/wavelet/build", json={"sequence": [1, "x"]})
    assert resp.status_code == 422 and "error" in resp.json()


def test_build_string_alphabet(client):
    body = client.post("/api/v1/wavelet/build",
                       json={"sequence": ["b", "a", "b", "c"]}).json()
    assert body["alphabet_size"] == 3 and body["kind"] == "str"


# ── access ─────────────────────────────────────────────────────────────────────────────

def test_access(built_client):
    assert built_client.get("/api/v1/wavelet/access", params={"i": 0}).json()["symbol"] == 3
    assert built_client.get("/api/v1/wavelet/access", params={"i": 1}).json()["symbol"] == 1


def test_access_missing_i_422(built_client):
    assert built_client.get("/api/v1/wavelet/access").status_code == 422


def test_access_out_of_range_422(built_client):
    resp = built_client.get("/api/v1/wavelet/access", params={"i": 5})   # n=5, valid [0,4]
    assert resp.status_code == 422 and "error" in resp.json()


# ── rank ─────────────────────────────────────────────────────────────────────────────────

def test_rank(built_client):
    body = built_client.post("/api/v1/wavelet/rank", json={"symbol": 1, "i": 5}).json()
    assert body["rank"] == 2                                  # ones at positions 1,3


def test_rank_absent_symbol_zero(built_client):
    assert built_client.post("/api/v1/wavelet/rank", json={"symbol": 99, "i": 5}).json()["rank"] == 0


def test_rank_missing_fields_422(built_client):
    assert built_client.post("/api/v1/wavelet/rank", json={"symbol": 1}).status_code == 422


def test_rank_index_out_of_range_422(built_client):
    resp = built_client.post("/api/v1/wavelet/rank", json={"symbol": 1, "i": 6})
    assert resp.status_code == 422 and "error" in resp.json()


# ── quantile ─────────────────────────────────────────────────────────────────────────────

def test_quantile_smallest(built_client):
    assert built_client.post("/api/v1/wavelet/quantile", json={"i": 0, "j": 5, "k": 1}).json()["symbol"] == 1


def test_quantile_largest(built_client):
    assert built_client.post("/api/v1/wavelet/quantile", json={"i": 0, "j": 5, "k": 5}).json()["symbol"] == 5


def test_quantile_missing_fields_422(built_client):
    assert built_client.post("/api/v1/wavelet/quantile", json={"i": 0, "j": 5}).status_code == 422


def test_quantile_bad_range_422(built_client):
    resp = built_client.post("/api/v1/wavelet/quantile", json={"i": 2, "j": 2, "k": 1})
    assert resp.status_code == 422 and "error" in resp.json()


def test_quantile_k_out_of_range_422(built_client):
    resp = built_client.post("/api/v1/wavelet/quantile", json={"i": 0, "j": 2, "k": 3})
    assert resp.status_code == 422 and "error" in resp.json()


# ── stats ───────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/wavelet/stats").json()) == {
        "size", "alphabet_size", "height", "kind"}


def test_stats_defaults(client):
    s = client.get("/api/v1/wavelet/stats").json()
    assert s["size"] == 0 and s["alphabet_size"] == 0 and s["kind"] is None


# ── reset ───────────────────────────────────────────────────────────────────────────

def test_reset_clears(built_client):
    body = built_client.request("DELETE", "/api/v1/wavelet/reset").json()
    assert body["size"] == 0 and body["alphabet_size"] == 0


def test_reset_no_body(client):
    assert client.request("DELETE", "/api/v1/wavelet/reset").status_code == 200


# ── string round-trip ────────────────────────────────────────────────────────────────────

def test_string_rank_and_quantile(client):
    client.post("/api/v1/wavelet/build", json={"sequence": ["cat", "ant", "cat", "bee"]})
    assert client.post("/api/v1/wavelet/rank", json={"symbol": "cat", "i": 4}).json()["rank"] == 2
    assert client.post("/api/v1/wavelet/quantile", json={"i": 0, "j": 4, "k": 1}).json()["symbol"] == "ant"


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
                  "prioritysample", "cuckoohash", "splaytree", "rankselect"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
