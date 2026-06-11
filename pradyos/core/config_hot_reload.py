"""Phase 21A — Sovereign Config Hot-Reload.

Watches a YAML/JSON config file for changes and hot-reloads:
  - intent_engine rules
  - scheduler jobs
  - policy rules

No external dependencies: uses json.loads as YAML fallback (tests write
JSON; real deployments may install PyYAML for true YAML support).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("pradyos.core.config_hot_reload")

# ---------------------------------------------------------------------------
# Try to import PyYAML; fall back to json.loads (JSON is valid YAML subset)
# ---------------------------------------------------------------------------
try:
    import yaml as _yaml  # type: ignore

    def _parse_config(text: str) -> dict:
        return _yaml.safe_load(text) or {}

except ImportError:  # pragma: no cover — PyYAML not installed in stdlib-only env

    def _parse_config(text: str) -> dict:  # type: ignore[misc]
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("Config must be a JSON/YAML mapping at the top level")
        return result


# ---------------------------------------------------------------------------
# ReloadResult
# ---------------------------------------------------------------------------


@dataclass
class ReloadResult:
    """Outcome of a single config reload attempt."""

    success: bool
    timestamp: float
    changes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "timestamp": self.timestamp,
            "changes": list(self.changes),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# ConfigHotReloader
# ---------------------------------------------------------------------------


class ConfigHotReloader:
    """File-watcher that hot-reloads config sections into running components.

    Parameters
    ----------
    config_path:
        Path to the YAML/JSON config file to watch.
    intent_engine:
        Optional intent engine; must expose ``load_rules(rules)`` method.
    scheduler:
        Optional scheduler; must expose ``add_job(**job)`` method.
    policy_engine:
        Optional policy engine; must expose ``load_rules(rules)`` method.
    poll_interval:
        Seconds between mtime polls (default 5.0).
    """

    def __init__(
        self,
        config_path: str | Path,
        intent_engine: Any | None = None,
        scheduler: Any | None = None,
        policy_engine: Any | None = None,
        poll_interval: float = 5.0,
    ) -> None:
        self._config_path = Path(config_path)
        self._intent_engine = intent_engine
        self._scheduler = scheduler
        self._policy_engine = policy_engine
        self._poll_interval = poll_interval

        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._last_result: ReloadResult | None = None
        self._last_mtime: float | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> ReloadResult:
        """Read the config file and apply all present sections.

        Returns a ReloadResult.  On any exception, success=False and the
        error message is captured; no exception is propagated to the caller.
        """
        ts = time.time()
        try:
            raw = self._config_path.read_text(encoding="utf-8")
            config: dict = _parse_config(raw)
        except Exception as exc:  # noqa: BLE001
            result = ReloadResult(success=False, timestamp=ts, error=str(exc))
            with self._lock:
                self._last_result = result
            return result

        changes: list[str] = []

        # ── intent_rules ────────────────────────────────────────────────
        if "intent_rules" in config and self._intent_engine is not None:
            try:
                rules = config["intent_rules"]
                self._intent_engine.load_rules(rules)
                changes.append(f"intent_rules: loaded {len(rules)} rule(s)")
            except Exception as exc:  # noqa: BLE001
                result = ReloadResult(success=False, timestamp=ts, error=str(exc))
                with self._lock:
                    self._last_result = result
                return result

        # ── scheduler_jobs ──────────────────────────────────────────────
        if "scheduler_jobs" in config and self._scheduler is not None:
            try:
                jobs = config["scheduler_jobs"]
                for job in jobs:
                    self._scheduler.add_job(**job)
                changes.append(f"scheduler_jobs: added {len(jobs)} job(s)")
            except Exception as exc:  # noqa: BLE001
                result = ReloadResult(success=False, timestamp=ts, error=str(exc))
                with self._lock:
                    self._last_result = result
                return result

        # ── policy_rules ────────────────────────────────────────────────
        if "policy_rules" in config and self._policy_engine is not None:
            try:
                rules = config["policy_rules"]
                self._policy_engine.load_rules(rules)
                changes.append(f"policy_rules: loaded {len(rules)} rule(s)")
            except Exception as exc:  # noqa: BLE001
                result = ReloadResult(success=False, timestamp=ts, error=str(exc))
                with self._lock:
                    self._last_result = result
                return result

        result = ReloadResult(success=True, timestamp=ts, changes=changes)
        with self._lock:
            self._last_result = result
        log.info("Config reloaded from %s — changes: %s", self._config_path, changes)
        return result

    def start(self) -> None:
        """Start the background polling thread (daemon=True)."""
        with self._lock:
            if self._running:
                return
            self._running = True

        self._thread = threading.Thread(
            target=self._poll_loop,
            name="config-hot-reload",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "ConfigHotReloader started — watching %s every %.1fs",
            self._config_path,
            self._poll_interval,
        )

    def stop(self) -> None:
        """Stop the background polling thread."""
        with self._lock:
            self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=self._poll_interval + 2)
        self._thread = None
        log.info("ConfigHotReloader stopped.")

    def last_result(self) -> ReloadResult | None:
        """Return the most-recent ReloadResult, or None if never loaded."""
        with self._lock:
            return self._last_result

    def status(self) -> dict[str, Any]:
        """Return a status dict suitable for JSON serialisation."""
        with self._lock:
            lr = self._last_result
            running = self._running
        return {
            "running": running,
            "config_path": str(self._config_path),
            "last_reload": lr.to_dict() if lr is not None else None,
            "poll_interval": self._poll_interval,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Background loop: reload when file mtime changes."""
        while True:
            with self._lock:
                if not self._running:
                    break
            try:
                mtime = self._config_path.stat().st_mtime
                if self._last_mtime is None or mtime != self._last_mtime:
                    self._last_mtime = mtime
                    self.load()
            except Exception:  # noqa: BLE001
                pass  # file missing / unreadable — silently retry
            time.sleep(self._poll_interval)
