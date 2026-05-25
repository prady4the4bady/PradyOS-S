"""Sovereign Advisor — Phase 7D Oracle Intelligence.

Reads the audit tail + metrics snapshot and produces ranked Recommendation
objects that suggest campaigns, investigations, or maintenance actions.

Pattern recognition:
  - High task-failure rate   → suggest investigation campaign
  - Failed tasks with retries → suggest re-running those tasks
  - Campaigns succeeded after retries → suggest re-running similar
  - Long idle periods         → suggest maintenance campaign
  - No oracle plans produced  → suggest connectivity check

Windows-safe: all stdlib, no signals, no AF_UNIX, no fork.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("pradyos.oracle.advisor")

__all__ = ["SovereignAdvisor", "Recommendation"]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    """A single ranked advisor recommendation."""
    rank: int
    title: str
    reason: str
    confidence_pct: float          # 0–100
    suggested_campaign_goal: str   # short imperative description for a new campaign

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "title": self.title,
            "reason": self.reason,
            "confidence_pct": round(self.confidence_pct, 1),
            "suggested_campaign_goal": self.suggested_campaign_goal,
        }


# ---------------------------------------------------------------------------
# Advisor
# ---------------------------------------------------------------------------

class SovereignAdvisor:
    """Reads audit tail and metrics to produce ranked Recommendations.

    Parameters
    ----------
    audit_log:
        An ``EventAuditLog`` (or any object with ``.tail(n)``).
    metrics_registry:
        A ``MetricsRegistry`` (or any object with ``.snapshot()``).
    campaign_registry:
        A ``CampaignRegistry`` (or any object with ``.recent(n)``). Optional.
    """

    AUDIT_TAIL_SIZE = 200

    def __init__(
        self,
        audit_log: Any | None = None,
        metrics_registry: Any | None = None,
        campaign_registry: Any | None = None,
    ) -> None:
        self._audit = audit_log
        self._metrics = metrics_registry
        self._campaigns = campaign_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(self, n: int = 5) -> list[Recommendation]:
        """Produce up to *n* ranked Recommendations.

        Returns an empty list if no signals are available.
        Recommendations are sorted by confidence_pct descending.
        """
        candidates: list[Recommendation] = []

        audit_events = self._fetch_audit_events()
        metrics_snap = self._fetch_metrics()
        recent_campaigns = self._fetch_campaigns()

        # --- Analysis passes ---
        candidates.extend(self._analyze_failure_rate(metrics_snap))
        candidates.extend(self._analyze_retried_tasks(audit_events))
        candidates.extend(self._analyze_idle(audit_events))
        candidates.extend(self._analyze_oracle_health(metrics_snap, audit_events))
        candidates.extend(self._analyze_campaign_patterns(recent_campaigns, audit_events))

        # De-duplicate by title and sort
        seen: set[str] = set()
        unique: list[Recommendation] = []
        for r in sorted(candidates, key=lambda x: x.confidence_pct, reverse=True):
            if r.title not in seen:
                seen.add(r.title)
                unique.append(r)

        # Re-rank after dedup
        for i, rec in enumerate(unique[:n], start=1):
            rec.rank = i

        return unique[:n]

    # ------------------------------------------------------------------
    # Data fetching (safe — never raises)
    # ------------------------------------------------------------------

    def _fetch_audit_events(self) -> list[Any]:
        if self._audit is None:
            return []
        try:
            return self._audit.tail(self.AUDIT_TAIL_SIZE)
        except Exception as e:  # noqa: BLE001
            log.debug("Advisor: audit fetch failed: %s", e)
            return []

    def _fetch_metrics(self) -> dict[str, Any]:
        if self._metrics is None:
            return {}
        try:
            return self._metrics.snapshot()
        except Exception as e:  # noqa: BLE001
            log.debug("Advisor: metrics fetch failed: %s", e)
            return {}

    def _fetch_campaigns(self) -> list[Any]:
        if self._campaigns is None:
            return []
        try:
            return self._campaigns.recent(50)
        except Exception as e:  # noqa: BLE001
            log.debug("Advisor: campaign fetch failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Analysis passes
    # ------------------------------------------------------------------

    def _analyze_failure_rate(self, snap: dict[str, Any]) -> list[Recommendation]:
        """High task failure rate → investigate."""
        results: list[Recommendation] = []
        succeeded = _metric_value(snap, "tasks_succeeded")
        failed = _metric_value(snap, "tasks_failed")
        total = succeeded + failed
        if total < 3:
            return results

        rate = failed / total
        if rate >= 0.5:
            confidence = min(95.0, 60.0 + rate * 35.0)
            results.append(Recommendation(
                rank=0,
                title="High task failure rate detected",
                reason=(
                    f"{int(failed)} of {int(total)} tasks failed "
                    f"({rate * 100:.0f}% failure rate). "
                    "System may be misconfigured or a dependency is unavailable."
                ),
                confidence_pct=confidence,
                suggested_campaign_goal=(
                    "Run diagnostic campaign to identify and remediate root cause of task failures"
                ),
            ))
        elif rate >= 0.2:
            confidence = 40.0 + rate * 50.0
            results.append(Recommendation(
                rank=0,
                title="Elevated task failure rate",
                reason=(
                    f"{int(failed)} of {int(total)} tasks failed "
                    f"({rate * 100:.0f}% failure rate). "
                    "Consider reviewing failing task configurations."
                ),
                confidence_pct=confidence,
                suggested_campaign_goal=(
                    "Audit task configurations and retry failed tasks"
                ),
            ))
        return results

    def _analyze_retried_tasks(self, events: list[Any]) -> list[Recommendation]:
        """Tasks that failed but then retry-succeeded → suggest targeted re-run."""
        results: list[Recommendation] = []
        retry_events = [
            e for e in events
            if _event_action(e) == "retry:plan" or "retry" in _event_action(e).lower()
        ]
        failed_tasks = [
            e for e in events
            if _event_action(e) in ("task_failed", "task_FAILED")
               or "task_fail" in _event_action(e).lower()
        ]

        if failed_tasks:
            count = len(failed_tasks)
            confidence = min(85.0, 40.0 + count * 5.0)
            results.append(Recommendation(
                rank=0,
                title=f"Re-run {count} failed task(s)",
                reason=(
                    f"{count} task failure event(s) recorded in the audit tail. "
                    "Re-running failed tasks may succeed if transient failures have cleared."
                ),
                confidence_pct=confidence,
                suggested_campaign_goal=(
                    f"Re-submit and execute {count} previously failed task(s)"
                ),
            ))

        if retry_events:
            confidence = min(70.0, 30.0 + len(retry_events) * 8.0)
            results.append(Recommendation(
                rank=0,
                title="Retry activity detected — review retry policies",
                reason=(
                    f"{len(retry_events)} retry event(s) found in audit. "
                    "Frequent retries indicate intermittent failures; "
                    "consider increasing circuit breaker thresholds or fixing root cause."
                ),
                confidence_pct=confidence,
                suggested_campaign_goal=(
                    "Review and tune retry policies for high-retry subsystems"
                ),
            ))
        return results

    def _analyze_idle(self, events: list[Any]) -> list[Recommendation]:
        """Long idle period → suggest maintenance."""
        results: list[Recommendation] = []
        if not events:
            results.append(Recommendation(
                rank=0,
                title="No recent activity — system appears idle",
                reason="No audit events found. System may be idle or audit log is empty.",
                confidence_pct=30.0,
                suggested_campaign_goal="Run maintenance health-check campaign",
            ))
            return results

        now = time.time()
        latest_ts = max(
            (getattr(e, "timestamp", 0.0) for e in events),
            default=0.0,
        )
        idle_sec = now - latest_ts

        if idle_sec > 3600:  # 1 hour
            confidence = min(75.0, 30.0 + (idle_sec / 3600) * 5.0)
            results.append(Recommendation(
                rank=0,
                title="System idle for extended period",
                reason=(
                    f"No activity for {idle_sec / 3600:.1f} hour(s). "
                    "Consider running maintenance checks."
                ),
                confidence_pct=confidence,
                suggested_campaign_goal=(
                    "Run system maintenance and health-validation campaign"
                ),
            ))
        return results

    def _analyze_oracle_health(
        self, snap: dict[str, Any], events: list[Any]
    ) -> list[Recommendation]:
        """Oracle errors detected → suggest connectivity check."""
        results: list[Recommendation] = []
        ok_count = _metric_value(snap, "oracle_plans_ok")
        err_count = _metric_value(snap, "oracle_plans_error")

        if err_count > 0 and ok_count == 0:
            results.append(Recommendation(
                rank=0,
                title="Oracle planner unreachable",
                reason=(
                    f"{int(err_count)} Oracle plan error(s) with 0 successes. "
                    "Ollama service may be offline or misconfigured."
                ),
                confidence_pct=88.0,
                suggested_campaign_goal=(
                    "Restart Oracle/Ollama service and verify connectivity"
                ),
            ))
        elif err_count > 0:
            err_rate = err_count / (ok_count + err_count)
            if err_rate > 0.3:
                confidence = min(80.0, 50.0 + err_rate * 40.0)
                results.append(Recommendation(
                    rank=0,
                    title="Oracle planner experiencing elevated errors",
                    reason=(
                        f"{int(err_count)} plan error(s), {int(ok_count)} success(es) "
                        f"({err_rate * 100:.0f}% error rate). "
                        "Oracle may be degraded."
                    ),
                    confidence_pct=confidence,
                    suggested_campaign_goal=(
                        "Investigate and stabilise Oracle planner connectivity"
                    ),
                ))
        return results

    def _analyze_campaign_patterns(
        self, campaigns: list[Any], events: list[Any]
    ) -> list[Recommendation]:
        """Look for re-runnable campaigns (succeeded after retry)."""
        results: list[Recommendation] = []
        if not campaigns:
            return results

        # Campaigns that succeeded
        succeeded = [
            c for c in campaigns
            if str(getattr(getattr(c, "status", None), "value", "")).lower() == "succeeded"
        ]
        failed = [
            c for c in campaigns
            if str(getattr(getattr(c, "status", None), "value", "")).lower() in ("failed", "rolled_back")
        ]

        if failed:
            count = len(failed)
            confidence = min(78.0, 35.0 + count * 10.0)
            names = ", ".join(
                getattr(c, "name", "?") for c in failed[:3]
            )
            results.append(Recommendation(
                rank=0,
                title=f"{count} failed campaign(s) may be retryable",
                reason=(
                    f"Campaigns [{names}] ended in failure. "
                    "Retrying after fixing underlying issues may succeed."
                ),
                confidence_pct=confidence,
                suggested_campaign_goal=(
                    f"Re-execute {count} previously failed campaign(s) after root-cause fix"
                ),
            ))

        if len(succeeded) > 3:
            results.append(Recommendation(
                rank=0,
                title="System stable — consider expanding automation",
                reason=(
                    f"{len(succeeded)} campaigns succeeded recently. "
                    "System is healthy; a good time to plan new automation campaigns."
                ),
                confidence_pct=45.0,
                suggested_campaign_goal=(
                    "Design and launch next automation campaign for new system goal"
                ),
            ))

        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _metric_value(snap: dict[str, Any], name: str) -> float:
    """Extract the numeric value from a metrics snapshot entry."""
    entry = snap.get(name)
    if entry is None:
        return 0.0
    if isinstance(entry, dict):
        return float(entry.get("value", 0.0))
    return float(getattr(entry, "value", 0.0))


def _event_action(event: Any) -> str:
    """Return the action string of an audit event (safe)."""
    return str(getattr(event, "action", ""))
