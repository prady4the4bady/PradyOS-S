"""CampaignArchiver — Phase 6 Resilience Layer.

Flushes FINISHED (SUCCEEDED/FAILED) campaigns older than a TTL from the
CampaignRegistry into per-day JSONL archive files.

Archive path: var/archive/campaigns_YYYYMMDD.jsonl

Windows-safe: all paths via pathlib, datetime.timezone.utc for timestamps.
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("pradyos.campaign.archiver")

_ROOT = Path(__file__).resolve().parents[2]
_ARCHIVE_DIR = _ROOT / "var" / "archive"

# Campaign statuses considered terminal (eligible for archiving)
_TERMINAL_STATUSES = {"succeeded", "failed", "rolled_back", "cancelled"}


class CampaignArchiver:
    """Archive old terminal campaigns from a registry to per-day JSONL files.

    Usage::

        archiver = CampaignArchiver()
        archiver.archive_old(registry, ttl_seconds=3600)
    """

    def __init__(self, archive_dir: Path | None = None) -> None:
        self._archive_dir = archive_dir or _ARCHIVE_DIR
        self._archive_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def archive_old(self, registry: Any, ttl_seconds: float = 3600.0) -> int:
        """Remove campaigns older than *ttl_seconds* from *registry*.

        A campaign is eligible if:
          - its status is terminal (SUCCEEDED / FAILED / ROLLED_BACK / CANCELLED)
          - its ``finished_at`` or ``created_at`` timestamp is older than
            ``now - ttl_seconds``

        Returns the number of campaigns archived.
        """
        now = time.time()
        cutoff = now - ttl_seconds
        archived = 0

        for campaign in list(registry.all()):
            status_val = (
                campaign.status.value
                if hasattr(campaign.status, "value")
                else str(campaign.status)
            ).lower()

            if status_val not in _TERMINAL_STATUSES:
                continue

            # Determine age by finished_at falling back to created_at
            age_ts = getattr(campaign, "finished_at", None) or getattr(campaign, "created_at", None)
            if age_ts is None:
                continue
            if float(age_ts) > cutoff:
                continue

            # Convert to dict for archiving
            raw = self._campaign_to_dict(campaign)
            date_str = datetime.datetime.fromtimestamp(
                float(age_ts), tz=datetime.timezone.utc
            ).strftime("%Y%m%d")

            self._write_to_archive(date_str, raw)

            # Remove from live registry
            campaign_id = getattr(campaign, "campaign_id", None)
            if campaign_id:
                registry.delete(campaign_id)
                log.info(
                    "Archived campaign [%s] status=%s age=%.0fs",
                    campaign_id[:8], status_val, now - float(age_ts),
                )
                archived += 1

        return archived

    def load_archive(self, date_str: str) -> list[dict[str, Any]]:
        """Return all archived campaign dicts for *date_str* (YYYYMMDD)."""
        path = self._archive_path(date_str)
        if not path.exists():
            return []
        results: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _archive_path(self, date_str: str) -> Path:
        return self._archive_dir / f"campaigns_{date_str}.jsonl"

    def _write_to_archive(self, date_str: str, raw: dict[str, Any]) -> None:
        path = self._archive_path(date_str)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(raw, default=str, separators=(",", ":")) + "\n")
        except OSError as e:
            log.error("CampaignArchiver write failed: %s", e)

    @staticmethod
    def _campaign_to_dict(campaign: Any) -> dict[str, Any]:
        """Convert a Campaign object to a plain dict."""
        if hasattr(campaign, "to_dict"):
            try:
                return campaign.to_dict()
            except Exception:  # noqa: BLE001
                pass
        # Fallback: grab common fields
        return {
            "campaign_id":  getattr(campaign, "campaign_id", "?"),
            "name":         getattr(campaign, "name", ""),
            "status":       str(getattr(campaign, "status", "")),
            "created_at":   getattr(campaign, "created_at", None),
            "finished_at":  getattr(campaign, "finished_at", None),
        }
