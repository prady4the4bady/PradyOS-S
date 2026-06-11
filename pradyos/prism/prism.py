"""PRISM artifact-production lifecycle.

An artifact is ``request``-ed (status ``requested``), moved to ``generating`` by
``start``, then either ``deliver``-ed (status ``ready``, with an output ref and a
first variant) or ``fail``-ed. ``add_variant`` appends alternative outputs to a
ready artifact. ``gallery`` returns the ready artifacts.
"""

from __future__ import annotations

import threading
from typing import Any

ARTIFACT_KINDS = ("doc", "image", "site", "report", "code", "deck", "app")


class PrismError(RuntimeError):
    """Base class for PRISM failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


class _Artifact:
    __slots__ = ("id", "kind", "brief", "status", "variants", "failure")

    def __init__(self, art_id: str, kind: str, brief: str) -> None:
        self.id = art_id
        self.kind = kind
        self.brief = brief
        self.status = "requested"  # requested | generating | ready | failed
        self.variants: list[str] = []
        self.failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "brief": self.brief,
            "status": self.status,
            "variants": list(self.variants),
            "variant_count": len(self.variants),
            "failure": self.failure,
        }


class Prism:
    """Produces creative artifacts through a generation lifecycle."""

    def __init__(self) -> None:
        self._artifacts: dict[str, _Artifact] = {}
        self._lock = threading.RLock()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def request(self, art_id: str, kind: str, brief: str) -> dict[str, Any]:
        if not _is_str(art_id):
            raise PrismError("artifact id must be a non-empty string")
        if kind not in ARTIFACT_KINDS:
            raise PrismError(f"kind must be one of {ARTIFACT_KINDS}")
        if not _is_str(brief):
            raise PrismError("brief must be a non-empty string")
        with self._lock:
            if art_id in self._artifacts:
                raise PrismError(f"artifact {art_id!r} already exists")
            a = _Artifact(art_id, kind, brief)
            self._artifacts[art_id] = a
            return a.to_dict()

    def start(self, art_id: str) -> dict[str, Any]:
        with self._lock:
            a = self._require(art_id)
            if a.status != "requested":
                raise PrismError(f"artifact {art_id!r} is not requested (status={a.status})")
            a.status = "generating"
            return a.to_dict()

    def deliver(self, art_id: str, output_ref: str) -> dict[str, Any]:
        if not _is_str(output_ref):
            raise PrismError("output_ref must be a non-empty string")
        with self._lock:
            a = self._require(art_id)
            if a.status != "generating":
                raise PrismError(f"artifact {art_id!r} is not generating (status={a.status})")
            a.status = "ready"
            a.variants.append(output_ref)
            return a.to_dict()

    def add_variant(self, art_id: str, output_ref: str) -> dict[str, Any]:
        if not _is_str(output_ref):
            raise PrismError("output_ref must be a non-empty string")
        with self._lock:
            a = self._require(art_id)
            if a.status != "ready":
                raise PrismError(f"artifact {art_id!r} is not ready (status={a.status})")
            a.variants.append(output_ref)
            return a.to_dict()

    def fail(self, art_id: str, reason: str = "") -> dict[str, Any]:
        with self._lock:
            a = self._require(art_id)
            if a.status in ("ready", "failed"):
                raise PrismError(f"artifact {art_id!r} is terminal ({a.status})")
            a.status = "failed"
            a.failure = reason or "generation failed"
            return a.to_dict()

    # ── introspection ────────────────────────────────────────────────────────

    def artifact(self, art_id: str) -> dict[str, Any]:
        with self._lock:
            return self._require(art_id).to_dict()

    def gallery(self, kind: str | None = None) -> list[dict[str, Any]]:
        if kind is not None and kind not in ARTIFACT_KINDS:
            raise PrismError(f"kind must be one of {ARTIFACT_KINDS}")
        with self._lock:
            return [
                a.to_dict()
                for a in self._artifacts.values()
                if a.status == "ready" and (kind is None or a.kind == kind)
            ]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_status: dict[str, int] = {}
            for a in self._artifacts.values():
                by_status[a.status] = by_status.get(a.status, 0) + 1
            return {"artifacts": len(self._artifacts), "by_status": by_status}

    def reset(self) -> None:
        with self._lock:
            self._artifacts.clear()

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, art_id: str) -> _Artifact:
        a = self._artifacts.get(art_id)
        if a is None:
            raise PrismError(f"unknown artifact {art_id!r}")
        return a
