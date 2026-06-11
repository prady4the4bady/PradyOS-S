from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class StepError(Exception):
    """Raised when a pipeline step cannot transform an event."""

    def __init__(self, step_name: str, original_event: dict, message: str) -> None:
        super().__init__(message)
        self.step_name = step_name
        self.original_event = dict(original_event) if original_event else {}
        self.message = message


# ── built-in transforms (dict → dict, never mutate input) ────────────────────


def set_field(event: dict, *, key: str, value: Any) -> dict:
    out = dict(event)
    out[key] = value
    return out


def delete_field(event: dict, *, key: str) -> dict:
    return {k: v for k, v in event.items() if k != key}


def rename_field(event: dict, *, old: str, new: str) -> dict:
    if old not in event:
        return dict(event)  # silent no-op when source key is absent
    out = dict(event)
    out[new] = out.pop(old)
    return out


def uppercase_field(event: dict, *, key: str) -> dict:
    if key not in event:
        raise StepError("uppercase_field", event, f"missing key: {key!r}")
    val = event[key]
    if not isinstance(val, str):
        raise StepError(
            "uppercase_field",
            event,
            f"value at {key!r} is not str (got {type(val).__name__})",
        )
    out = dict(event)
    out[key] = val.upper()
    return out


def lowercase_field(event: dict, *, key: str) -> dict:
    if key not in event:
        raise StepError("lowercase_field", event, f"missing key: {key!r}")
    val = event[key]
    if not isinstance(val, str):
        raise StepError(
            "lowercase_field",
            event,
            f"value at {key!r} is not str (got {type(val).__name__})",
        )
    out = dict(event)
    out[key] = val.lower()
    return out


_TRANSFORMS: dict[str, Callable[..., dict]] = {
    "set_field": set_field,
    "delete_field": delete_field,
    "rename_field": rename_field,
    "uppercase_field": uppercase_field,
    "lowercase_field": lowercase_field,
}


# ── Step / Chain / Registry ──────────────────────────────────────────────────


@dataclass
class Step:
    name: str
    transform_type: str
    params: dict = field(default_factory=dict)


@dataclass
class PipelineChain:
    name: str
    steps: list[Step] = field(default_factory=list)

    def run(self, event: dict) -> dict:
        current = dict(event)  # shallow copy; never mutate caller's dict
        for step in self.steps:
            fn = _TRANSFORMS.get(step.transform_type)
            if fn is None:
                raise StepError(
                    step.name,
                    event,
                    f"unknown transform_type: {step.transform_type!r}",
                )
            try:
                current = fn(current, **(step.params or {}))
            except StepError as exc:
                # Re-raise with the step's user-given name and the ORIGINAL
                # event (not the intermediate `current`) for traceability.
                raise StepError(step.name, event, exc.message) from exc
            except Exception as exc:
                raise StepError(step.name, event, str(exc)) from exc
        return current


class PipelineRegistry:
    def __init__(self) -> None:
        self._chains: dict[str, PipelineChain] = {}
        self._lock = threading.Lock()

    def register(self, chain: PipelineChain) -> None:
        with self._lock:
            self._chains[chain.name] = chain

    def get(self, name: str) -> PipelineChain | None:
        with self._lock:
            return self._chains.get(name)

    def delete(self, name: str) -> bool:
        with self._lock:
            return self._chains.pop(name, None) is not None

    def list_chains(self) -> list[str]:
        with self._lock:
            return sorted(self._chains.keys())

    def run(self, name: str, event: dict) -> dict:
        with self._lock:
            chain = self._chains.get(name)
        if chain is None:
            raise KeyError(name)
        return chain.run(event)
