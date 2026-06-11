from __future__ import annotations

import collections
import math
import threading
import time
from dataclasses import dataclass


@dataclass
class SignalPoint:
    value: float
    recorded_at: float

    def to_dict(self) -> dict:
        return {"value": self.value, "recorded_at": self.recorded_at}


class SignalAggregator:
    def __init__(self, max_total: int = 10000) -> None:
        self._max_total = max_total
        self._signals: dict[str, collections.deque[SignalPoint]] = {}
        self._lock = threading.Lock()

    def record(self, name: str, value: float, timestamp: float | None = None) -> SignalPoint:
        pt = SignalPoint(
            value=value, recorded_at=timestamp if timestamp is not None else time.time()
        )
        with self._lock:
            if name not in self._signals:
                self._signals[name] = collections.deque(maxlen=self._max_total)
            self._signals[name].append(pt)
        return pt

    def get(self, name: str, limit: int = 100) -> list[SignalPoint]:
        with self._lock:
            if name not in self._signals:
                return []
            points = list(self._signals[name])
        return points[-limit:]

    def list_signals(self) -> list[dict]:
        with self._lock:
            names = sorted(self._signals.keys())
            result = []
            for n in names:
                dq = self._signals[n]
                count = len(dq)
                latest = dq[-1].value if count > 0 else None
                result.append({"name": n, "count": count, "latest": latest})
        return result

    def stats(self, name: str) -> dict | None:
        with self._lock:
            if name not in self._signals:
                return None
            values = [pt.value for pt in self._signals[name]]
        n = len(values)
        if n == 0:
            return None
        mn = min(values)
        mx = max(values)
        mean = sum(values) / n
        if n == 1:
            stddev = 0.0
        else:
            variance = sum((x - mean) ** 2 for x in values) / n
            stddev = math.sqrt(variance)
        return {
            "name": name,
            "count": n,
            "min": mn,
            "max": mx,
            "mean": mean,
            "stddev": stddev,
        }
