"""CampaignRegistry — persist campaigns to var/state/campaigns.jsonl.

Uses JSON Lines format (one JSON object per line). Each write appends
or rewrites the line for the affected campaign. The registry loads all
campaigns on startup and maintains an in-memory index.

Windows-safe: all paths via pathlib, no hardcoded separators.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from pradyos.campaign.model import Campaign, CampaignStatus

log = logging.getLogger("pradyos.campaign.registry")

_DEFAULT_PATH = Path(__file__).parent.parent.parent / "var" / "state" / "campaigns.jsonl"


class CampaignRegistry:
    """Thread-safe JSONL-backed registry of Campaigns."""

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path or _DEFAULT_PATH
        self._campaigns: dict[str, Campaign] = {}
        self._lock = threading.Lock()
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, campaign: Campaign) -> None:
        """Persist *campaign* (insert or update)."""
        with self._lock:
            self._campaigns[campaign.campaign_id] = campaign
            self._flush()

    def delete(self, campaign_id: str) -> bool:
        """Remove a campaign from the registry. Returns True if found."""
        with self._lock:
            if campaign_id not in self._campaigns:
                return False
            del self._campaigns[campaign_id]
            self._flush()
            return True

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, campaign_id: str) -> Campaign | None:
        with self._lock:
            return self._campaigns.get(campaign_id)

    def all(self) -> list[Campaign]:
        with self._lock:
            return list(self._campaigns.values())

    def by_status(self, status: CampaignStatus) -> list[Campaign]:
        with self._lock:
            return [c for c in self._campaigns.values() if c.status == status]

    def active(self) -> list[Campaign]:
        """Return campaigns that are in a non-terminal state."""
        with self._lock:
            return [c for c in self._campaigns.values() if not c.status.terminal]

    def recent(self, limit: int = 20) -> list[Campaign]:
        """Return the most recently created campaigns."""
        with self._lock:
            cs = sorted(self._campaigns.values(), key=lambda c: c.created_at, reverse=True)
            return cs[:limit]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            counts: dict[str, int] = {}
            for c in self._campaigns.values():
                counts[c.status.value] = counts.get(c.status.value, 0) + 1
            return {
                "total": len(self._campaigns),
                **{f"status.{k}": v for k, v in counts.items()},
            }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _flush(self) -> None:
        """Rewrite the entire JSONL file atomically."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".jsonl.tmp")
            lines: list[str] = []
            for c in self._campaigns.values():
                lines.append(json.dumps(c.to_dict(), default=str))
            tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as e:
            log.error("CampaignRegistry flush failed: %s", e)

    def _load(self) -> None:
        """Load campaigns from JSONL on startup."""
        if not self._path.exists():
            return
        try:
            text = self._path.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    c = Campaign.from_dict(d)
                    self._campaigns[c.campaign_id] = c
                except Exception as e:  # noqa: BLE001
                    log.debug("Skipping malformed campaign line: %s", e)
            log.info("CampaignRegistry loaded %d campaigns from %s", len(self._campaigns), self._path)
        except OSError as e:
            log.debug("CampaignRegistry load skipped: %s", e)
