"""Sovereign Rate-Limit Shield — sliding-window in-memory rate limiter.

Phase 23A: Thread-safe, per-(client_id, endpoint) sliding window counter.
No external dependencies — stdlib only.
"""

from __future__ import annotations

import threading
import time as _time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    """Result returned by RateLimiter.check()."""

    allowed: bool
    client_id: str
    endpoint: str
    limit: int
    window_secs: float
    current: int  # requests recorded in current window
    retry_after: float | None  # seconds until oldest expires; None if allowed

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "client_id": self.client_id,
            "endpoint": self.endpoint,
            "limit": self.limit,
            "window_secs": self.window_secs,
            "current": self.current,
            "retry_after": self.retry_after,
        }


class RateLimiter:
    """Sliding-window, in-memory rate limiter.

    Parameters
    ----------
    default_limit:
        Maximum requests allowed per (client_id, endpoint) per window.
    default_window:
        Sliding window size in seconds.
    """

    def __init__(
        self,
        default_limit: int = 60,
        default_window: float = 60.0,
    ) -> None:
        self._default_limit = default_limit
        self._default_window = default_window
        # Per-endpoint rules: endpoint -> {"limit": int, "window": float}
        self._rules: dict[str, dict] = {}
        # Hit store: (client_id, endpoint) -> list of timestamps
        self._hits: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def set_rule(self, endpoint: str, limit: int, window: float) -> None:
        """Set (or overwrite) per-endpoint rate-limit rule."""
        with self._lock:
            self._rules[endpoint] = {"limit": limit, "window": window}

    def get_rules(self) -> dict[str, dict]:
        """Return a copy of the current rules dict (mutation-safe)."""
        with self._lock:
            return {k: dict(v) for k, v in self._rules.items()}

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def check(
        self,
        client_id: str,
        endpoint: str,
        clock: Callable[[], float] = _time.time,
    ) -> RateLimitResult:
        """Apply sliding-window rate limit for (client_id, endpoint).

        Parameters
        ----------
        client_id:
            Opaque identifier for the requesting client.
        endpoint:
            The endpoint/resource being accessed.
        clock:
            Optional injectable callable returning current epoch seconds.
            Defaults to ``time.time``.  Use a fake clock in tests.

        Returns
        -------
        RateLimitResult
            ``allowed=True`` if permitted (hit recorded).
            ``allowed=False`` if limit exceeded (hit NOT recorded).
        """
        now = clock()
        with self._lock:
            # Resolve rule for this endpoint
            if endpoint in self._rules:
                limit = self._rules[endpoint]["limit"]
                window = self._rules[endpoint]["window"]
            else:
                limit = self._default_limit
                window = self._default_window

            key = (client_id, endpoint)
            timestamps = self._hits.get(key, [])

            # Prune timestamps outside the sliding window
            cutoff = now - window
            timestamps = [t for t in timestamps if t > cutoff]

            current = len(timestamps)

            if current < limit:
                # Allowed — record hit
                timestamps.append(now)
                self._hits[key] = timestamps
                return RateLimitResult(
                    allowed=True,
                    client_id=client_id,
                    endpoint=endpoint,
                    limit=limit,
                    window_secs=window,
                    current=current + 1,
                    retry_after=None,
                )
            else:
                # Denied — do NOT record hit; compute retry_after
                self._hits[key] = timestamps  # store pruned list
                oldest = min(timestamps)
                retry_after = (oldest + window) - now
                if retry_after < 0.0:
                    retry_after = 0.0
                return RateLimitResult(
                    allowed=False,
                    client_id=client_id,
                    endpoint=endpoint,
                    limit=limit,
                    window_secs=window,
                    current=current,
                    retry_after=retry_after,
                )

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self, client_id: str, endpoint: str | None = None) -> None:
        """Clear hit timestamps for *client_id*.

        If *endpoint* is given, clear only that (client_id, endpoint) key.
        Otherwise clear ALL keys for this client_id.
        """
        with self._lock:
            if endpoint is not None:
                self._hits.pop((client_id, endpoint), None)
            else:
                to_delete = [k for k in self._hits if k[0] == client_id]
                for k in to_delete:
                    del self._hits[k]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return a summary of current limiter state."""
        with self._lock:
            active_clients = len({k[0] for k in self._hits if self._hits[k]})
            total_hits = sum(len(v) for v in self._hits.values())
            return {
                "active_clients": active_clients,
                "total_hits": total_hits,
                "rules": {k: dict(v) for k, v in self._rules.items()},
                "default_limit": self._default_limit,
                "default_window": self._default_window,
            }
