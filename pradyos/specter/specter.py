"""SPECTER web-action flow runner.

``plan`` enforces fallback-first routing: if a target has an API, the mode is
``api`` (preferred); otherwise ``browser``. A browser flow is a list of steps;
``step`` advances the cursor and records the checkpoint (last completed step),
``extract`` stores scraped state, and ``fail_step`` retries the current step up
to ``MAX_ATTEMPTS`` before the flow fails.
"""

from __future__ import annotations

import threading
from typing import Any

STEP_KINDS = ("navigate", "login", "fill", "click", "extract")
MAX_ATTEMPTS = 3


class SpecterError(RuntimeError):
    """Base class for SPECTER failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


class _Flow:
    __slots__ = ("id", "target", "steps", "cursor", "checkpoint", "attempts", "status", "state")

    def __init__(self, flow_id: str, target: str, steps: list[dict[str, str]]) -> None:
        self.id = flow_id
        self.target = target
        self.steps = steps
        self.cursor = 0
        self.checkpoint = -1  # index of last completed step
        self.attempts = 0  # attempts on the current step
        self.status = "ready"  # ready | running | done | failed
        self.state: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "steps": [dict(s) for s in self.steps],
            "cursor": self.cursor,
            "checkpoint": self.checkpoint,
            "attempts": self.attempts,
            "status": self.status,
            "state": dict(self.state),
            "remaining": max(0, len(self.steps) - self.cursor),
        }


class Specter:
    """Runs checkpointed web-action flows, API-first by policy."""

    def __init__(self) -> None:
        self._flows: dict[str, _Flow] = {}
        self._lock = threading.RLock()

    # ── routing ──────────────────────────────────────────────────────────────

    @staticmethod
    def plan(target: str, has_api: bool) -> dict[str, Any]:
        """Fallback-first: prefer an API; fall back to a browser flow."""
        if not _is_str(target):
            raise SpecterError("target must be a non-empty string")
        if not isinstance(has_api, bool):
            raise SpecterError("has_api must be a bool")
        mode = "api" if has_api else "browser"
        reason = (
            "API available — preferred over a brittle browser flow"
            if has_api
            else "no API — falling back to a browser flow"
        )
        return {"target": target, "mode": mode, "reason": reason}

    # ── flows ────────────────────────────────────────────────────────────────

    def create_flow(self, flow_id: str, target: str, steps: Any) -> dict[str, Any]:
        if not _is_str(flow_id):
            raise SpecterError("flow_id must be a non-empty string")
        if not _is_str(target):
            raise SpecterError("target must be a non-empty string")
        if not isinstance(steps, list | tuple) or not steps:
            raise SpecterError("steps must be a non-empty list")
        norm: list[dict[str, str]] = []
        for s in steps:
            if not isinstance(s, dict) or s.get("kind") not in STEP_KINDS:
                raise SpecterError(f"each step needs kind in {STEP_KINDS}")
            norm.append({"kind": s["kind"], "arg": str(s.get("arg", ""))})
        with self._lock:
            if flow_id in self._flows:
                raise SpecterError(f"flow {flow_id!r} already exists")
            f = _Flow(flow_id, target, norm)
            self._flows[flow_id] = f
            return f.to_dict()

    def step(self, flow_id: str) -> dict[str, Any]:
        """Execute the current step and advance the checkpoint."""
        with self._lock:
            f = self._require(flow_id)
            if f.status in ("done", "failed"):
                raise SpecterError(f"flow {flow_id!r} is terminal ({f.status})")
            if f.cursor >= len(f.steps):
                raise SpecterError(f"flow {flow_id!r} has no more steps")
            f.checkpoint = f.cursor
            f.cursor += 1
            f.attempts = 0
            f.status = "done" if f.cursor >= len(f.steps) else "running"
            return f.to_dict()

    def extract(self, flow_id: str, key: str, value: Any) -> dict[str, Any]:
        if not _is_str(key):
            raise SpecterError("extract key must be a non-empty string")
        with self._lock:
            f = self._require(flow_id)
            f.state[key] = value
            return f.to_dict()

    def fail_step(self, flow_id: str, reason: str = "") -> dict[str, Any]:
        """Retry the current step; after MAX_ATTEMPTS the flow fails."""
        with self._lock:
            f = self._require(flow_id)
            if f.status in ("done", "failed"):
                raise SpecterError(f"flow {flow_id!r} is terminal ({f.status})")
            f.attempts += 1
            if f.attempts >= MAX_ATTEMPTS:
                f.status = "failed"
                f.state["_failure"] = reason or "max attempts exceeded"
            else:
                f.status = "running"
            return f.to_dict()

    # ── introspection ────────────────────────────────────────────────────────

    def flow(self, flow_id: str) -> dict[str, Any]:
        with self._lock:
            return self._require(flow_id).to_dict()

    def flows(self) -> list[dict[str, Any]]:
        with self._lock:
            return [f.to_dict() for f in self._flows.values()]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_status: dict[str, int] = {}
            for f in self._flows.values():
                by_status[f.status] = by_status.get(f.status, 0) + 1
            return {"flows": len(self._flows), "by_status": by_status}

    def reset(self) -> None:
        with self._lock:
            self._flows.clear()

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, flow_id: str) -> _Flow:
        f = self._flows.get(flow_id)
        if f is None:
            raise SpecterError(f"unknown flow {flow_id!r}")
        return f
