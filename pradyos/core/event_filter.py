from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any


_VALID_OPS = {
    "eq", "neq", "gt", "lt", "gte", "lte",
    "contains", "startswith", "endswith", "regex",
}

_MISSING = object()


def _resolve(field: str, event: dict) -> Any:
    """Resolve a dot-notation field path against an event dict.
    Return _MISSING (sentinel) if any segment is absent."""
    if not field:
        return _MISSING
    cur: Any = event
    for part in field.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _is_numeric(value: Any) -> bool:
    """True for int/float, excluding bool (which subclasses int)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compare(op: str, resolved: Any, target: Any) -> bool:
    """Apply op between resolved (event value) and target (rule value)."""
    if op == "eq":
        return resolved == target
    if op == "neq":
        return resolved != target

    if op in ("gt", "lt", "gte", "lte"):
        if _is_numeric(resolved) and _is_numeric(target):
            a, b = float(resolved), float(target)
        else:
            a, b = str(resolved), str(target)
        if op == "gt":
            return a > b
        if op == "lt":
            return a < b
        if op == "gte":
            return a >= b
        if op == "lte":
            return a <= b

    if op == "contains":
        return str(target) in str(resolved)
    if op == "startswith":
        return str(resolved).startswith(str(target))
    if op == "endswith":
        return str(resolved).endswith(str(target))
    if op == "regex":
        try:
            return re.search(str(target), str(resolved)) is not None
        except re.error:
            return False

    return False  # unknown op


@dataclass
class FilterRule:
    field: str
    op: str
    value: Any

    def matches(self, event: dict) -> bool:
        resolved = _resolve(self.field, event)
        if resolved is _MISSING:
            return False
        if self.op not in _VALID_OPS:
            return False
        try:
            return _compare(self.op, resolved, self.value)
        except Exception:
            return False

    def to_dict(self) -> dict:
        return {"field": self.field, "op": self.op, "value": self.value}


class EventFilter:
    def __init__(self, rules: list[FilterRule], mode: str = "AND") -> None:
        if mode not in ("AND", "OR"):
            raise ValueError(f"mode must be AND or OR, got {mode!r}")
        self._rules = list(rules)
        self._mode = mode

    def match(self, event: dict) -> bool:
        if not self._rules:
            return True
        if self._mode == "AND":
            return all(r.matches(event) for r in self._rules)
        return any(r.matches(event) for r in self._rules)

    def to_dict(self) -> dict:
        return {
            "rules": [r.to_dict() for r in self._rules],
            "mode": self._mode,
        }

    @property
    def rules(self) -> list[FilterRule]:
        return list(self._rules)

    @property
    def mode(self) -> str:
        return self._mode


class EventFilterRegistry:
    def __init__(self) -> None:
        self._filters: dict[str, EventFilter] = {}
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        rules: list[FilterRule],
        mode: str = "AND",
    ) -> EventFilter:
        filt = EventFilter(rules, mode)
        with self._lock:
            self._filters[name] = filt
        return filt

    def get(self, name: str) -> EventFilter | None:
        with self._lock:
            return self._filters.get(name)

    def delete(self, name: str) -> bool:
        with self._lock:
            return self._filters.pop(name, None) is not None

    def list_names(self) -> list[str]:
        with self._lock:
            return sorted(self._filters.keys())

    def apply(self, name: str, events: list[dict]) -> list[dict]:
        with self._lock:
            filt = self._filters.get(name)
        if filt is None:
            raise KeyError(name)
        return [e for e in events if filt.match(e)]
