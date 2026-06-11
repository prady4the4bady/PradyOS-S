"""PRISM tests — artifact production lifecycle verified."""

from __future__ import annotations

import pytest

from pradyos.prism import Prism, PrismError


def _p() -> Prism:
    return Prism()


def test_request_starts_requested():
    a = _p().request("a1", "report", "Q4 empire health")
    assert a["status"] == "requested" and a["kind"] == "report"


def test_request_validation():
    p = _p()
    with pytest.raises(PrismError):
        p.request("", "doc", "b")
    with pytest.raises(PrismError):
        p.request("a", "hologram", "b")
    with pytest.raises(PrismError):
        p.request("a", "doc", "")


def test_full_lifecycle_to_ready():
    p = _p()
    p.request("a", "site", "landing page")
    assert p.start("a")["status"] == "generating"
    a = p.deliver("a", "s3://artifacts/a/v1")
    assert a["status"] == "ready" and a["variant_count"] == 1


def test_deliver_requires_generating():
    p = _p()
    p.request("a", "doc", "b")
    with pytest.raises(PrismError):
        p.deliver("a", "ref")  # not started


def test_add_variant_only_when_ready():
    p = _p()
    p.request("a", "deck", "pitch")
    p.start("a")
    with pytest.raises(PrismError):
        p.add_variant("a", "v2")  # not ready yet
    p.deliver("a", "v1")
    a = p.add_variant("a", "v2")
    assert a["variant_count"] == 2 and a["variants"] == ["v1", "v2"]


def test_fail():
    p = _p()
    p.request("a", "image", "logo")
    p.start("a")
    a = p.fail("a", "model timeout")
    assert a["status"] == "failed" and a["failure"] == "model timeout"
    with pytest.raises(PrismError):
        p.fail("a")  # terminal


def test_gallery_only_ready():
    p = _p()
    p.request("a", "doc", "x")
    p.start("a")
    p.deliver("a", "ref")
    p.request("b", "doc", "y")  # still requested
    gallery = [a["id"] for a in p.gallery()]
    assert gallery == ["a"]
    assert p.gallery(kind="report") == []


def test_dupe_and_unknown():
    p = _p()
    p.request("a", "doc", "b")
    with pytest.raises(PrismError):
        p.request("a", "doc", "b")
    with pytest.raises(PrismError):
        p.artifact("ghost")


def test_stats_and_reset():
    p = _p()
    p.request("a", "doc", "b")
    p.start("a")
    s = p.stats()
    assert s["artifacts"] == 1 and s["by_status"]["generating"] == 1
    p.reset()
    assert p.stats()["artifacts"] == 0 and p.gallery() == []
