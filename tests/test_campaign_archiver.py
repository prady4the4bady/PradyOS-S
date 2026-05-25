"""Tests for Phase 6 CampaignArchiver.

Covers: archive triggers on TTL, registry shrinks, JSONL written, reload.
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pradyos.campaign.archiver import CampaignArchiver


# ---------------------------------------------------------------------------
# Fake Campaign / FakeRegistry for isolated testing
# ---------------------------------------------------------------------------


class _FakeCampaign:
    def __init__(
        self,
        campaign_id: str,
        status: str,
        age_seconds: float = 0.0,
    ) -> None:
        self.campaign_id = campaign_id
        self.status      = _FakeStatus(status)
        self.name        = f"camp_{campaign_id}"
        # finished_at = now - age_seconds
        self.finished_at = time.time() - age_seconds
        self.created_at  = self.finished_at - 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "name":        self.name,
            "status":      self.status.value,
            "created_at":  self.created_at,
            "finished_at": self.finished_at,
        }


class _FakeStatus:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value


class _FakeRegistry:
    def __init__(self, campaigns: list[_FakeCampaign]) -> None:
        self._data = {c.campaign_id: c for c in campaigns}

    def all(self) -> list[_FakeCampaign]:
        return list(self._data.values())

    def delete(self, campaign_id: str) -> bool:
        return bool(self._data.pop(campaign_id, None))

    def __len__(self) -> int:
        return len(self._data)


# ---------------------------------------------------------------------------
# Archive triggers on TTL
# ---------------------------------------------------------------------------


def test_archive_old_terminal_and_old(tmp_path):
    arch = CampaignArchiver(archive_dir=tmp_path / "archive")
    reg = _FakeRegistry([
        _FakeCampaign("c1", "succeeded", age_seconds=7200),  # 2h old → archive
        _FakeCampaign("c2", "failed",    age_seconds=7200),  # archive
        _FakeCampaign("c3", "running",   age_seconds=7200),  # not terminal → skip
        _FakeCampaign("c4", "succeeded", age_seconds=10),    # too fresh → skip
    ])
    n = arch.archive_old(reg, ttl_seconds=3600)
    assert n == 2


def test_archive_skips_non_terminal(tmp_path):
    arch = CampaignArchiver(archive_dir=tmp_path / "archive")
    reg = _FakeRegistry([
        _FakeCampaign("c1", "running",  age_seconds=9999),
        _FakeCampaign("c2", "pending",  age_seconds=9999),
        _FakeCampaign("c3", "planning", age_seconds=9999),
    ])
    n = arch.archive_old(reg, ttl_seconds=1)
    assert n == 0
    assert len(reg) == 3


def test_archive_skips_fresh_terminal(tmp_path):
    arch = CampaignArchiver(archive_dir=tmp_path / "archive")
    reg = _FakeRegistry([
        _FakeCampaign("c1", "succeeded", age_seconds=10),   # 10s old < ttl 3600
    ])
    n = arch.archive_old(reg, ttl_seconds=3600)
    assert n == 0
    assert len(reg) == 1


# ---------------------------------------------------------------------------
# Registry shrinks after archive
# ---------------------------------------------------------------------------


def test_registry_shrinks(tmp_path):
    arch = CampaignArchiver(archive_dir=tmp_path / "archive")
    reg = _FakeRegistry([
        _FakeCampaign("a", "succeeded", age_seconds=4000),
        _FakeCampaign("b", "failed",    age_seconds=4000),
        _FakeCampaign("c", "running",   age_seconds=4000),
    ])
    assert len(reg) == 3
    arch.archive_old(reg, ttl_seconds=3600)
    assert len(reg) == 1
    remaining = reg.all()
    assert remaining[0].campaign_id == "c"


# ---------------------------------------------------------------------------
# JSONL file written correctly
# ---------------------------------------------------------------------------


def test_jsonl_written(tmp_path):
    archive_dir = tmp_path / "archive"
    arch = CampaignArchiver(archive_dir=archive_dir)
    reg = _FakeRegistry([
        _FakeCampaign("x1", "succeeded", age_seconds=7200),
        _FakeCampaign("x2", "failed",    age_seconds=7200),
    ])
    arch.archive_old(reg, ttl_seconds=3600)

    # Find any .jsonl file in archive dir
    files = list(archive_dir.glob("campaigns_*.jsonl"))
    assert len(files) >= 1, "Expected at least one archive file"

    all_lines = []
    for f in files:
        all_lines.extend(f.read_text(encoding="utf-8").strip().splitlines())

    assert len(all_lines) == 2
    ids = {json.loads(l)["campaign_id"] for l in all_lines}
    assert "x1" in ids
    assert "x2" in ids


def test_jsonl_filename_contains_date(tmp_path):
    archive_dir = tmp_path / "archive"
    arch = CampaignArchiver(archive_dir=archive_dir)
    reg = _FakeRegistry([
        _FakeCampaign("z1", "succeeded", age_seconds=7200),
    ])
    arch.archive_old(reg, ttl_seconds=3600)
    files = list(archive_dir.glob("campaigns_????????.jsonl"))
    assert files, "Expected campaigns_YYYYMMDD.jsonl file"
    name = files[0].name
    date_part = name[len("campaigns_"):len("campaigns_") + 8]
    assert date_part.isdigit() and len(date_part) == 8


# ---------------------------------------------------------------------------
# load_archive
# ---------------------------------------------------------------------------


def test_load_archive_returns_list(tmp_path):
    archive_dir = tmp_path / "archive"
    arch = CampaignArchiver(archive_dir=archive_dir)
    camp = _FakeCampaign("r1", "succeeded", age_seconds=7200)
    reg = _FakeRegistry([camp])
    arch.archive_old(reg, ttl_seconds=3600)

    # Derive the expected date from the campaign's own finished_at timestamp
    # to avoid date-boundary failures near midnight UTC.
    date_str = datetime.datetime.fromtimestamp(
        camp.finished_at, tz=datetime.timezone.utc
    ).strftime("%Y%m%d")
    results = arch.load_archive(date_str)
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["campaign_id"] == "r1"


def test_load_archive_missing_date_returns_empty(tmp_path):
    arch = CampaignArchiver(archive_dir=tmp_path / "archive")
    results = arch.load_archive("19700101")
    assert results == []


def test_load_archive_multiple_entries(tmp_path):
    archive_dir = tmp_path / "archive"
    arch = CampaignArchiver(archive_dir=archive_dir)
    camps = [
        _FakeCampaign("m1", "succeeded", age_seconds=7200),
        _FakeCampaign("m2", "failed",    age_seconds=7200),
        _FakeCampaign("m3", "cancelled", age_seconds=7200),
    ]
    reg = _FakeRegistry(camps)
    arch.archive_old(reg, ttl_seconds=3600)

    # Collect results across all archive files (date-boundary safe)
    all_results = []
    for f in archive_dir.glob("campaigns_*.jsonl"):
        date_str = f.stem[len("campaigns_"):]
        all_results.extend(arch.load_archive(date_str))
    assert len(all_results) == 3
    archived_ids = {r["campaign_id"] for r in all_results}
    assert archived_ids == {"m1", "m2", "m3"}


# ---------------------------------------------------------------------------
# All terminal statuses handled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["succeeded", "failed", "rolled_back", "cancelled"])
def test_all_terminal_statuses_archived(tmp_path, status):
    arch = CampaignArchiver(archive_dir=tmp_path / "archive")
    reg = _FakeRegistry([
        _FakeCampaign("t1", status, age_seconds=7200),
    ])
    n = arch.archive_old(reg, ttl_seconds=3600)
    assert n == 1
    assert len(reg) == 0
