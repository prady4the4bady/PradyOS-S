"""PRISM — tests for the /api/v1/prism endpoints in sovereign_web."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pradyos.sovereign_web import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


def _ready(client, aid="a", kind="report"):
    client.post("/api/v1/prism/request", json={"id": aid, "kind": kind, "brief": "b"})
    client.post("/api/v1/prism/start", json={"id": aid})
    return client.post("/api/v1/prism/deliver", json={"id": aid, "output_ref": "ref1"}).json()


def test_request_and_lifecycle(client):
    m = _ready(client)
    assert m["status"] == "ready" and m["variant_count"] == 1


def test_request_bad_kind_422(client):
    resp = client.post("/api/v1/prism/request", json={"id": "a", "kind": "hologram", "brief": "b"})
    assert resp.status_code == 422


def test_request_missing_422(client):
    assert client.post("/api/v1/prism/request", json={"id": "a"}).status_code == 422


def test_deliver_requires_generating_422(client):
    client.post("/api/v1/prism/request", json={"id": "a", "kind": "doc", "brief": "b"})
    assert (
        client.post("/api/v1/prism/deliver", json={"id": "a", "output_ref": "r"}).status_code == 422
    )


def test_variant(client):
    _ready(client)
    m = client.post("/api/v1/prism/variant", json={"id": "a", "output_ref": "ref2"}).json()
    assert m["variant_count"] == 2


def test_gallery_only_ready(client):
    _ready(client, "a", "report")
    client.post("/api/v1/prism/request", json={"id": "b", "kind": "doc", "brief": "b"})
    ids = [x["id"] for x in client.get("/api/v1/prism/gallery").json()["gallery"]]
    assert ids == ["a"]


def test_unknown_404(client):
    assert client.get("/api/v1/prism/artifact", params={"id": "nope"}).status_code == 404


def test_fail_and_stats(client):
    client.post("/api/v1/prism/request", json={"id": "a", "kind": "image", "brief": "b"})
    client.post("/api/v1/prism/start", json={"id": "a"})
    client.post("/api/v1/prism/fail", json={"id": "a", "reason": "timeout"})
    stats = client.get("/api/v1/prism/stats").json()
    assert stats["by_status"]["failed"] == 1
    after = client.delete("/api/v1/prism/reset").json()
    assert after["artifacts"] == 0
