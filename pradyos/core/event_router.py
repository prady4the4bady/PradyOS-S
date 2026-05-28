from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


_VALID_OPS = {
    "eq", "neq", "gt", "lt", "gte", "lte",
    "contains", "startswith", "endswith",
}

_MISSING = object()


def _match_one(event: dict, cond: dict) -> bool:
    """Apply a single condition dict to an event dict.
    Missing field: eq → False, neq → True, all other ops → False."""
    field_name = cond.get("field")
    op = cond.get("op")
    expected = cond.get("value")

    if field_name is None or op not in _VALID_OPS:
        return False

    actual = event.get(field_name, _MISSING)

    if actual is _MISSING:
        # Asymmetric: only `neq` is True when the field is absent.
        return op == "neq"

    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected

    if op in ("gt", "lt", "gte", "lte"):
        try:
            a, b = float(actual), float(expected)
        except (TypeError, ValueError):
            a, b = str(actual), str(expected)
        if op == "gt":
            return a > b
        if op == "lt":
            return a < b
        if op == "gte":
            return a >= b
        return a <= b  # lte

    if op == "contains":
        return str(expected) in str(actual)
    if op == "startswith":
        return str(actual).startswith(str(expected))
    if op == "endswith":
        return str(actual).endswith(str(expected))

    return False


@dataclass
class Route:
    name: str
    predicates: list[dict]
    destination: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "predicates": [dict(p) for p in self.predicates],
            "destination": self.destination,
        }

    def matches(self, event: dict) -> bool:
        """A route matches when EVERY predicate matches the event."""
        if not self.predicates:
            return True  # empty predicate list = match anything
        return all(_match_one(event, p) for p in self.predicates)


class EventRouter:
    def __init__(self, default_destination: str | None = None) -> None:
        self._routes: list[Route] = []
        self._lock = threading.Lock()
        self.default_destination = default_destination

    def add_route(
        self,
        name: str,
        predicates: list[dict],
        destination: str,
    ) -> Route:
        with self._lock:
            if any(r.name == name for r in self._routes):
                raise ValueError(f"route {name!r} already exists")
            preds = [dict(p) for p in (predicates or [])]
            route = Route(name=name, predicates=preds, destination=destination)
            self._routes.append(route)
            return route

    def remove_route(self, name: str) -> bool:
        with self._lock:
            for i, r in enumerate(self._routes):
                if r.name == name:
                    del self._routes[i]
                    return True
            return False

    def route(self, event: dict) -> list[str]:
        with self._lock:
            routes_snapshot = list(self._routes)
        matches: list[str] = []
        for r in routes_snapshot:
            if r.matches(event):
                matches.append(r.destination)
        if not matches and self.default_destination is not None:
            return [self.default_destination]
        return sorted(matches)

    def list_routes(self) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._routes]

    def count(self) -> int:
        with self._lock:
            return len(self._routes)


class RouterRegistry:
    def __init__(self) -> None:
        self._routers: dict[str, EventRouter] = {}
        self._lock = threading.Lock()

    def create(
        self,
        name: str,
        default_destination: str | None = None,
    ) -> EventRouter:
        with self._lock:
            if name in self._routers:
                raise ValueError(f"router {name!r} already exists")
            router = EventRouter(default_destination=default_destination)
            self._routers[name] = router
            return router

    def get(self, name: str) -> EventRouter | None:
        with self._lock:
            return self._routers.get(name)

    def delete(self, name: str) -> bool:
        with self._lock:
            return self._routers.pop(name, None) is not None

    def list_names(self) -> list[str]:
        with self._lock:
            return sorted(self._routers.keys())
