"""CHRONICLE SAGE tests — ledger + digest verified against ground truth."""

from __future__ import annotations

import pytest

from pradyos.chronicle_sage import ChronicleError, ChronicleSage


def _c() -> ChronicleSage:
    return ChronicleSage()


def test_record_assigns_increasing_seq():
    c = _c()
    e1 = c.record("deployment", "v1 shipped")
    e2 = c.record("changelog", "added X")
    assert e1["seq"] == 1 and e2["seq"] == 2 and e2["type"] == "changelog"


def test_record_validation():
    c = _c()
    with pytest.raises(ChronicleError):
        c.record("rumor", "x")
    with pytest.raises(ChronicleError):
        c.record("doc", "")
    with pytest.raises(ChronicleError):
        c.record("doc", "t", tags=[1, 2])


def test_record_rejects_string_tags():
    # a bare string must not be silently split into character "tags"
    c = _c()
    with pytest.raises(ChronicleError):
        c.record("doc", "t", tags="ops")


def test_entries_filter_by_type():
    c = _c()
    c.record("deployment", "d1")
    c.record("post_mortem", "p1")
    c.record("deployment", "d2")
    deploys = [e["title"] for e in c.entries(entry_type="deployment")]
    assert deploys == ["d1", "d2"]


def test_entries_filter_by_tag():
    c = _c()
    c.record("incident", "net outage", tags=["network", "sev1"])
    c.record("incident", "disk full", tags=["storage"])
    sel = [e["title"] for e in c.entries(tag="network")]
    assert sel == ["net outage"]


def test_entries_bad_type_raises():
    with pytest.raises(ChronicleError):
        _c().entries(entry_type="bogus")


def test_latest():
    c = _c()
    c.record("changelog", "a")
    c.record("deployment", "b")
    c.record("changelog", "c")
    assert c.latest()["title"] == "c"
    assert c.latest(entry_type="changelog")["title"] == "c"
    assert c.latest(entry_type="incident") is None


def test_digest_counts_and_recent():
    c = _c()
    c.record("deployment", "d1")
    c.record("deployment", "d2")
    c.record("post_mortem", "p1")
    c.record("improvement", "i1")
    d = c.digest(limit=2)
    assert d["total"] == 4
    assert d["by_type"]["deployment"] == 2 and d["by_type"]["post_mortem"] == 1
    assert [e["title"] for e in d["recent"]] == ["p1", "i1"]


def test_stats_and_reset():
    c = _c()
    c.record("doc", "readme")
    s = c.stats()
    assert s["entries"] == 1 and s["by_type"]["doc"] == 1
    c.reset()
    assert c.stats()["entries"] == 0 and c.digest()["total"] == 0
    # seq resets too
    assert c.record("doc", "again")["seq"] == 1
