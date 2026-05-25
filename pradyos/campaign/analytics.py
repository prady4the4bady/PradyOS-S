"""Campaign analytics — aggregate metrics over campaign history.

Provides read-only analytics computed from the CampaignRegistry.  All
methods accept a ``last_n`` parameter to limit the window to the N most
recently *created* campaigns.

Windows-safe: no file I/O, pure Python.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pradyos.campaign.registry import CampaignRegistry

from pradyos.campaign.model import CampaignStatus, NodeStatus


class CampaignAnalytics:
    """Aggregate analytics over campaigns in a :class:`CampaignRegistry`.

    Parameters
    ----------
    registry:
        A :class:`~pradyos.campaign.registry.CampaignRegistry` instance.
    """

    def __init__(self, registry: "CampaignRegistry") -> None:
        self.registry = registry

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _recent_n(self, n: int):
        """Return the *n* most recently created campaigns (any status)."""
        all_campaigns = self.registry.all()
        sorted_camps = sorted(all_campaigns, key=lambda c: c.created_at, reverse=True)
        return sorted_camps[:n]

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def success_rate(self, last_n: int = 100) -> float:
        """Fraction of terminal campaigns that succeeded in the last *n*.

        Returns 0.0 when no terminal campaigns exist.
        """
        campaigns = self._recent_n(last_n)
        terminal = [c for c in campaigns if c.status.terminal]
        if not terminal:
            return 0.0
        succeeded = sum(1 for c in terminal if c.status == CampaignStatus.SUCCEEDED)
        return succeeded / len(terminal)

    def avg_duration_s(self, last_n: int = 100) -> float:
        """Mean duration (seconds) of completed campaigns in the last *n*.

        Skips campaigns where either ``started_at`` or ``finished_at`` is None.
        Returns 0.0 when no valid durations exist.
        """
        campaigns = self._recent_n(last_n)
        durations: list[float] = []
        for c in campaigns:
            if c.started_at is not None and c.finished_at is not None:
                dur = c.finished_at - c.started_at
                if dur >= 0:
                    durations.append(dur)
        if not durations:
            return 0.0
        return sum(durations) / len(durations)

    def node_failure_histogram(self, last_n: int = 100) -> dict[str, int]:
        """Count of node failures by ``task_kind`` across the last *n* campaigns.

        Returns a dict mapping task_kind → failure count.
        """
        campaigns = self._recent_n(last_n)
        histogram: dict[str, int] = {}
        for c in campaigns:
            for node in c.nodes.values():
                if node.status == NodeStatus.FAILED:
                    kind = node.task.kind if node.task is not None else "unknown"
                    histogram[kind] = histogram.get(kind, 0) + 1
        return histogram

    def busiest_hours(self, last_n: int = 100) -> list[tuple[int, int]]:
        """Return ``(hour_0_23, count)`` pairs sorted by count descending.

        Based on the UTC hour extracted from ``campaign.created_at``.
        """
        campaigns = self._recent_n(last_n)
        hour_counts: dict[int, int] = {}
        for c in campaigns:
            try:
                hour = datetime.datetime.fromtimestamp(c.created_at, tz=datetime.timezone.utc).hour
            except (OSError, OverflowError, ValueError):
                continue
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        return sorted(hour_counts.items(), key=lambda kv: kv[1], reverse=True)

    def to_dict(self) -> dict[str, Any]:
        """Return all four metrics as a serialisable dict."""
        return {
            "success_rate": self.success_rate(),
            "avg_duration_s": self.avg_duration_s(),
            "node_failure_histogram": self.node_failure_histogram(),
            "busiest_hours": self.busiest_hours(),
        }
