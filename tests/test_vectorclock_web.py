"""Phase 75 — tests for the /api/v1/clocks endpoints in sovereign_web."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.core.vectorclock import VectorClock
from pradyos.sovereign_web import create_app


@pytest.fixture()
def client_no_clock():
    return TestClient(create_app())


@pytest.fixture()
def client_with_clock():
    return TestClient(create_app(vectorclock=VectorClock()))


# ── no clock configured ───────────────────────────────────────────────────────

def test_state_no_clock_returns_error(client_no_clock):
    assert "error" in client_no_clock.get("/api/v1/clocks").json()


def test_tick_no_clock_returns_error(client_no_clock):
    assert "error" in client_no_clock.post("/api/v1/clocks/tick", json={"actor": "A"}).json()


def test_merge_no_clock_returns_error(client_no_clock):
    assert "error" in client_no_clock.post("/api/v1/clocks/merge", json={"clock": {}}).json()


def test_compare_no_clock_returns_error(client_no_clock):
    assert "error" in client_no_clock.post("/api/v1/clocks/compare", json={"clock": {}}).json()


# ── state ─────────────────────────────────────────────────────────────────────

def test_state_has_expected_keys(client_with_clock):
    data = client_with_clock.get("/api/v1/clocks").json()
    for key in ("clock", "actors", "actor_count"):
        assert key in data


# ── tick ──────────────────────────────────────────────────────────────────────

def test_tick_increments(client_with_clock):
    resp = client_with_clock.post("/api/v1/clocks/tick", json={"actor": "A"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["value"] == 1
    assert body["clock"] == {"A": 1}


def test_tick_twice(client_with_clock):
    client_with_clock.post("/api/v1/clocks/tick", json={"actor": "A"})
    resp = client_with_clock.post("/api/v1/clocks/tick", json={"actor": "A"})
    assert resp.json()["value"] == 2


def test_tick_missing_actor_returns_422(client_with_clock):
    resp = client_with_clock.post("/api/v1/clocks/tick", json={})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_tick_then_state_reflects(client_with_clock):
    client_with_clock.post("/api/v1/clocks/tick", json={"actor": "A"})
    client_with_clock.post("/api/v1/clocks/tick", json={"actor": "B"})
    assert client_with_clock.get("/api/v1/clocks").json()["clock"] == {"A": 1, "B": 1}


# ── merge ─────────────────────────────────────────────────────────────────────

def test_merge_element_wise_max(client_with_clock):
    client_with_clock.post("/api/v1/clocks/tick", json={"actor": "A"})  # {A:1}
    resp = client_with_clock.post("/api/v1/clocks/merge", json={"clock": {"A": 5, "B": 2}})
    assert resp.status_code == 200
    assert resp.json()["clock"] == {"A": 5, "B": 2}


def test_merge_non_dict_returns_422(client_with_clock):
    resp = client_with_clock.post("/api/v1/clocks/merge", json={"clock": "nope"})
    assert resp.status_code == 422


def test_merge_bad_values_returns_422(client_with_clock):
    resp = client_with_clock.post("/api/v1/clocks/merge", json={"clock": {"A": -1}})
    assert resp.status_code == 422


# ── compare ───────────────────────────────────────────────────────────────────

def test_compare_before(client_with_clock):
    client_with_clock.post("/api/v1/clocks/tick", json={"actor": "A"})  # {A:1}
    resp = client_with_clock.post("/api/v1/clocks/compare", json={"clock": {"A": 2}})
    assert resp.json()["relation"] == "before"


def test_compare_concurrent(client_with_clock):
    client_with_clock.post("/api/v1/clocks/tick", json={"actor": "A"})  # {A:1}
    resp = client_with_clock.post("/api/v1/clocks/compare", json={"clock": {"B": 1}})
    assert resp.json()["relation"] == "concurrent"


def test_compare_equal(client_with_clock):
    client_with_clock.post("/api/v1/clocks/tick", json={"actor": "A"})  # {A:1}
    resp = client_with_clock.post("/api/v1/clocks/compare", json={"clock": {"A": 1}})
    assert resp.json()["relation"] == "equal"
