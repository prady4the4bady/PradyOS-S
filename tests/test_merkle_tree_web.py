"""Phase 77 — tests for the /api/v1/merkle endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.merkle_tree import MerkleTree
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_tree():
    return TestClient(create_app())


@pytest.fixture()
def client_with_tree():
    return TestClient(create_app(merkle_tree=MerkleTree()))


# ── no tree configured ────────────────────────────────────────────────────────

def test_stats_no_tree_returns_error(client_no_tree):
    assert "error" in client_no_tree.get("/api/v1/merkle").json()


def test_add_no_tree_returns_error(client_no_tree):
    assert "error" in client_no_tree.post("/api/v1/merkle/add", json={"item": "a"}).json()


def test_verify_no_tree_returns_error(client_no_tree):
    assert "error" in client_no_tree.post("/api/v1/merkle/verify", json={"item": "a"}).json()


def test_proof_no_tree_returns_error(client_no_tree):
    assert "error" in client_no_tree.post("/api/v1/merkle/proof", json={"item": "a"}).json()


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_has_expected_keys(client_with_tree):
    data = client_with_tree.get("/api/v1/merkle").json()
    for key in ("leaves", "height", "root"):
        assert key in data


def test_stats_empty_root_null(client_with_tree):
    assert client_with_tree.get("/api/v1/merkle").json()["root"] is None


# ── add ───────────────────────────────────────────────────────────────────────

def test_add_sets_root_and_count(client_with_tree):
    resp = client_with_tree.post("/api/v1/merkle/add", json={"item": "a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["leaves"] == 1
    assert body["root"] is not None


def test_add_missing_item_returns_422(client_with_tree):
    resp = client_with_tree.post("/api/v1/merkle/add", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


# ── verify ────────────────────────────────────────────────────────────────────

def test_verify_added_true(client_with_tree):
    for x in ("a", "b", "c"):
        client_with_tree.post("/api/v1/merkle/add", json={"item": x})
    assert client_with_tree.post("/api/v1/merkle/verify", json={"item": "b"}).json()["verified"] is True


def test_verify_unknown_false(client_with_tree):
    client_with_tree.post("/api/v1/merkle/add", json={"item": "a"})
    assert client_with_tree.post("/api/v1/merkle/verify", json={"item": "ghost"}).json()["verified"] is False


def test_verify_missing_item_returns_422(client_with_tree):
    assert client_with_tree.post("/api/v1/merkle/verify", json={}).status_code == 422


# ── proof ─────────────────────────────────────────────────────────────────────

def test_proof_returns_path_and_root(client_with_tree):
    for x in ("a", "b", "c", "d"):
        client_with_tree.post("/api/v1/merkle/add", json={"item": x})
    body = client_with_tree.post("/api/v1/merkle/proof", json={"item": "a"}).json()
    assert body["root"] is not None
    assert isinstance(body["proof"], list)
    assert len(body["proof"]) == 2  # ceil(log2(4))
    for step in body["proof"]:
        assert set(step) == {"hash", "side"}


def test_proof_unknown_returns_404(client_with_tree):
    client_with_tree.post("/api/v1/merkle/add", json={"item": "a"})
    resp = client_with_tree.post("/api/v1/merkle/proof", json={"item": "missing"})
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_proof_missing_item_returns_422(client_with_tree):
    assert client_with_tree.post("/api/v1/merkle/proof", json={}).status_code == 422


# ── round-trip ────────────────────────────────────────────────────────────────

def test_add_verify_proof_round_trip(client_with_tree):
    for i in range(5):
        client_with_tree.post("/api/v1/merkle/add", json={"item": f"leaf-{i}"})
    assert client_with_tree.post("/api/v1/merkle/verify", json={"item": "leaf-3"}).json()["verified"] is True
    proof = client_with_tree.post("/api/v1/merkle/proof", json={"item": "leaf-3"}).json()
    assert len(proof["proof"]) == 3  # ceil(log2(5))
