"""Phase 71 — Sovereign Anomaly Watch.

A real-time anomaly-detection watchdog for PradyOS services. Each *source* pairs
a name with a zero-argument ``metric_fn`` returning the current value of some
health metric (latency, error rate, queue depth, ...). On every :meth:`tick`
the watch polls each source, appends the reading to a bounded rolling window,
and — once at least ``min_samples`` readings have accumulated — scores the
latest reading with a scikit-learn :class:`~sklearn.ensemble.IsolationForest`
fitted on that window. Sources with fewer than ``min_samples`` readings report
``{"status": "warming_up"}`` instead of a score.

The Isolation Forest is the same algorithm the hardware-intel service uses;
here it runs purely in-process. scikit-learn (and its numpy backend) are the
only non-stdlib dependencies — readings are handed to the model as plain lists,
so this module imports nothing from numpy directly.

Thread-safe via a single non-reentrant ``threading.Lock``: the public surface
acquires it, and internal helpers invoked under the lock never re-acquire it.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Callable

from sklearn.ensemble import IsolationForest


MIN_SAMPLES = 10        # readings required before Isolation Forest scoring begins
DEFAULT_WINDOW = 256    # max readings retained per source (oldest evicted)


class SourceNotFoundError(Exception):
    """Raised when an operation references a source name that is not registered.

    The offending name is preserved on the ``name`` attribute.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"no such anomaly source: {name!r}")


class AnomalyWatch:
    """IsolationForest-backed watchdog over registered service metrics."""

    def __init__(
        self,
        *,
        min_samples: int = MIN_SAMPLES,
        window: int = DEFAULT_WINDOW,
        contamination: float | str = "auto",
        n_estimators: int = 100,
        random_state: int = 42,
    ) -> None:
        self._min_samples = max(2, int(min_samples))
        self._window = max(self._min_samples, int(window))
        self._contamination = contamination
        self._n_estimators = int(n_estimators)
        self._random_state = random_state
        self._fns: dict[str, Callable[[], float]] = {}
        self._samples: dict[str, deque[float]] = {}
        self._results: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── registration ────────────────────────────────────────────────────────
    def register_source(
        self,
        name: str,
        metric_fn: Callable[[], float],
        *,
        baseline: list[float] | None = None,
    ) -> None:
        """Register ``name`` with a zero-arg ``metric_fn`` returning its metric.

        An optional ``baseline`` of historical readings pre-seeds the rolling
        window so scoring can begin sooner (each baseline value counts toward
        ``min_samples``). Re-registering an existing name replaces it and resets
        its last result.
        """
        if not callable(metric_fn):
            raise TypeError("metric_fn must be callable")
        with self._lock:
            window: deque[float] = deque(maxlen=self._window)
            if baseline:
                for value in baseline:
                    window.append(float(value))
            self._fns[name] = metric_fn
            self._samples[name] = window
            self._results.pop(name, None)

    def deregister(self, name: str) -> None:
        """Remove a registered source. Raises :class:`SourceNotFoundError`."""
        with self._lock:
            if name not in self._fns:
                raise SourceNotFoundError(name)
            self._fns.pop(name, None)
            self._samples.pop(name, None)
            self._results.pop(name, None)

    # ── queries ─────────────────────────────────────────────────────────────
    def sources(self) -> list[str]:
        """Names of all registered sources, sorted."""
        with self._lock:
            return sorted(self._fns)

    def has_source(self, name: str) -> bool:
        with self._lock:
            return name in self._fns

    def sample_count(self, name: str) -> int:
        """Number of readings currently held for ``name``."""
        with self._lock:
            if name not in self._samples:
                raise SourceNotFoundError(name)
            return len(self._samples[name])

    # ── scoring ─────────────────────────────────────────────────────────────
    def tick(self) -> dict[str, dict]:
        """Poll every source, append its reading, and score the latest value.

        Returns a fresh ``{name: result}`` mapping (also retained for
        :meth:`get_status` / :meth:`get_anomalies`). A source with fewer than
        ``min_samples`` readings reports ``{"status": "warming_up", ...}``; a
        source whose ``metric_fn`` raises reports ``{"status": "error", ...}``
        without aborting the rest of the tick.
        """
        with self._lock:
            results: dict[str, dict] = {}
            for name, fn in self._fns.items():
                try:
                    value = float(fn())
                except Exception as exc:  # noqa: BLE001 — isolate a bad source
                    results[name] = {"status": "error", "error": str(exc)}
                    self._results[name] = results[name]
                    continue
                window = self._samples[name]
                window.append(value)
                results[name] = self._score_locked(value, window)
                self._results[name] = results[name]
            return results

    def _score_locked(self, value: float, window: deque[float]) -> dict:
        """Score ``value`` (already appended) against ``window``. Holds the lock."""
        n = len(window)
        if n < self._min_samples:
            return {"status": "warming_up", "samples": n, "value": round(value, 6)}
        features = [[v] for v in window]
        forest = IsolationForest(
            n_estimators=self._n_estimators,
            contamination=self._contamination,
            random_state=self._random_state,
        )
        forest.fit(features)
        prediction = int(forest.predict([[value]])[0])
        score = float(forest.decision_function([[value]])[0])
        return {
            "status": "scored",
            "anomaly": prediction == -1,
            "score": round(score, 6),
            "value": round(value, 6),
            "samples": n,
        }

    def get_anomalies(self) -> dict[str, dict]:
        """Latest results for sources currently flagged anomalous (copies)."""
        with self._lock:
            return {
                name: dict(result)
                for name, result in self._results.items()
                if result.get("anomaly")
            }

    def get_status(self) -> dict[str, dict]:
        """Latest per-source result from the most recent :meth:`tick` (copies)."""
        with self._lock:
            return {name: dict(result) for name, result in self._results.items()}

    def clear(self) -> None:
        """Drop all registered sources, windows, and results."""
        with self._lock:
            self._fns.clear()
            self._samples.clear()
            self._results.clear()
