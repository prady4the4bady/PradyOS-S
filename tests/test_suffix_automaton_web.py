"""Phase 151 — tests for the /api/v1/suffixautomaton endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.suffix_automaton import SuffixAutomaton
from pradyos.sovereign_web import create_app


def _brute(s):
    return {s[i:j] for i in range(len(s)) for j in range(i + 1, len(s) + 1)}


@pytest.fixture()
def client():
    return TestClient(create_app())


@pytest.fixture()
def filled_client():
    return TestClient(create_app(suffix_automaton=SuffixAutomaton("mississippi")))


# ── build ─────────────────────────────────────────────────────────────────────────────────

def test_build_returns_stats(client):
    body = client.post("/api/v1/suffixautomaton/build", json={"text": "abcabc"}).json()
    assert body["length"] == 6 and body["distinct_substrings"] == len(_brute("abcabc"))


def test_build_missing_422(client):
    assert client.post("/api/v1/suffixautomaton/build", json={}).status_code == 422


def test_build_non_str_422(client):
    resp = client.post("/api/v1/suffixautomaton/build", json={"text": 123})
    assert resp.status_code == 422 and "error" in resp.json()


# ── extend ───────────────────────────────────────────────────────────────────────────────

def test_extend_returns_state(client):
    body = client.post("/api/v1/suffixautomaton/extend", json={"ch": "a"}).json()
    assert body["length"] == 1 and body["num_states"] >= 2


def test_extend_missing_422(client):
    assert client.post("/api/v1/suffixautomaton/extend", json={}).status_code == 422


def test_extend_multichar_422(client):
    resp = client.post("/api/v1/suffixautomaton/extend", json={"ch": "ab"})
    assert resp.status_code == 422 and "error" in resp.json()


# ── contains ─────────────────────────────────────────────────────────────────────────────

def test_contains_true(filled_client):
    assert filled_client.get("/api/v1/suffixautomaton/contains", params={"pattern": "issi"}).json()["contains"] is True


def test_contains_false(filled_client):
    assert filled_client.get("/api/v1/suffixautomaton/contains", params={"pattern": "xyz"}).json()["contains"] is False


def test_contains_full(filled_client):
    assert filled_client.get("/api/v1/suffixautomaton/contains", params={"pattern": "mississippi"}).json()["contains"] is True


def test_contains_empty_true(filled_client):
    assert filled_client.get("/api/v1/suffixautomaton/contains", params={"pattern": ""}).json()["contains"] is True


# ── distinct_substrings ──────────────────────────────────────────────────────────────────

def test_distinct_substrings(filled_client):
    body = filled_client.get("/api/v1/suffixautomaton/distinct_substrings").json()
    assert body["distinct_substrings"] == len(_brute("mississippi"))


def test_distinct_substrings_empty(client):
    assert client.get("/api/v1/suffixautomaton/distinct_substrings").json()["distinct_substrings"] == 0


# ── stats / reset ─────────────────────────────────────────────────────────────────────────

def test_stats_keys(client):
    assert set(client.get("/api/v1/suffixautomaton/stats").json()) == \
        {"num_states", "length", "distinct_substrings", "transitions"}


def test_stats_after_build(filled_client):
    s = filled_client.get("/api/v1/suffixautomaton/stats").json()
    assert s["length"] == 11 and s["distinct_substrings"] == len(_brute("mississippi"))


def test_reset_clears(filled_client):
    body = filled_client.request("DELETE", "/api/v1/suffixautomaton/reset").json()
    assert body["num_states"] == 1 and body["length"] == 0 and body["distinct_substrings"] == 0


# ── round-trip / workflow ─────────────────────────────────────────────────────────────────

def test_build_then_query(client):
    client.post("/api/v1/suffixautomaton/build", json={"text": "banana"})
    assert client.get("/api/v1/suffixautomaton/contains", params={"pattern": "ana"}).json()["contains"] is True
    assert client.get("/api/v1/suffixautomaton/distinct_substrings").json()["distinct_substrings"] == len(_brute("banana"))


def test_extend_then_contains(client):
    for ch in "abc":
        client.post("/api/v1/suffixautomaton/extend", json={"ch": ch})
    assert client.get("/api/v1/suffixautomaton/contains", params={"pattern": "bc"}).json()["contains"] is True
    assert client.get("/api/v1/suffixautomaton/contains", params={"pattern": "ac"}).json()["contains"] is False


# ── regression ────────────────────────────────────────────────────────────────────────────

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
                  "prioritysample", "cuckoohash", "splaytree", "rankselect", "wavelet",
                  "skewheap", "intervaltree", "sparsetable", "kdtree", "radixtree",
                  "suffixarray", "ahocorasick", "xortrie", "minmaxheap", "cartesiantree",
                  "fenwick2d", "sqrtdecomp", "lichao", "perseg", "pairingheap"):
        assert client.get(f"/api/v1/{stats}/stats").status_code == 200
    assert client.get("/api/v1/morris/stats").status_code == 200
