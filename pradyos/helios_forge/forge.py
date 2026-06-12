"""HELIOS FORGE build state machine.

Each approved project becomes a build that walks the ordered ``STAGES``. The
forge gates the two safety-critical transitions:

  * ``tested -> validated`` requires a recorded test result with **zero
    failures** (the mandatory test gate), and
  * ``validated -> staged`` requires **every milestone complete**.

``staged`` is terminal. Artifacts (code/test/doc/config) and milestones are
tracked per build; ``manifest`` returns an immutable snapshot.
"""

from __future__ import annotations

import threading
from typing import Any

STAGES: tuple[str, ...] = (
    "planned",
    "scaffolded",
    "coded",
    "tested",
    "validated",
    "staged",
)

_ARTIFACT_KINDS = ("code", "test", "doc", "config", "build")


class ForgeError(RuntimeError):
    """Base class for HELIOS FORGE failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


class _Build:
    __slots__ = ("id", "project", "stage", "milestones", "artifacts", "tests")

    def __init__(self, build_id: str, project: str) -> None:
        self.id = build_id
        self.project = project
        self.stage = "planned"
        self.milestones: dict[str, bool] = {}  # name -> done
        self.artifacts: list[dict[str, str]] = []
        self.tests: dict[str, int] | None = None  # {"passed": p, "failed": f}

    def manifest(self) -> dict[str, Any]:
        done = sum(1 for v in self.milestones.values() if v)
        total = len(self.milestones)
        return {
            "id": self.id,
            "project": self.project,
            "stage": self.stage,
            "stage_index": STAGES.index(self.stage),
            "milestones": [{"name": n, "done": d} for n, d in self.milestones.items()],
            "milestone_progress": {"done": done, "total": total},
            "artifacts": [dict(a) for a in self.artifacts],
            "tests": dict(self.tests) if self.tests is not None else None,
            "is_terminal": self.stage == "staged",
        }


class HeliosForge:
    """Drives approved projects from plan to staged deliverable."""

    def __init__(self) -> None:
        self._builds: dict[str, _Build] = {}
        self._lock = threading.RLock()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def create(self, build_id: str, project: str) -> dict[str, Any]:
        """Start a new build for an approved ``project``."""
        if not _is_str(build_id):
            raise ForgeError("build_id must be a non-empty string")
        if not _is_str(project):
            raise ForgeError("project must be a non-empty string")
        with self._lock:
            if build_id in self._builds:
                raise ForgeError(f"build {build_id!r} already exists")
            b = _Build(build_id, project)
            self._builds[build_id] = b
            return b.manifest()

    def advance(self, build_id: str) -> dict[str, Any]:
        """Move the build to the next stage, enforcing the gates."""
        with self._lock:
            b = self._require(build_id)
            idx = STAGES.index(b.stage)
            if idx >= len(STAGES) - 1:
                raise ForgeError(f"build {build_id!r} is already staged (terminal)")
            nxt = STAGES[idx + 1]
            if nxt == "validated":
                if (
                    b.tests is None
                    or b.tests.get("failed", 1) != 0
                    or b.tests.get("passed", 0) <= 0
                ):
                    raise ForgeError("cannot validate: tests not recorded green (gate)")
            if nxt == "staged":
                incomplete = [n for n, d in b.milestones.items() if not d]
                if incomplete:
                    raise ForgeError(f"cannot stage: milestones incomplete {incomplete}")
            b.stage = nxt
            return b.manifest()

    # ── milestones & artifacts ───────────────────────────────────────────────

    def add_milestone(self, build_id: str, name: str) -> dict[str, Any]:
        if not _is_str(name):
            raise ForgeError("milestone name must be a non-empty string")
        with self._lock:
            b = self._require(build_id)
            self._ensure_mutable(b)
            b.milestones.setdefault(name, False)
            return b.manifest()

    def complete_milestone(self, build_id: str, name: str) -> dict[str, Any]:
        with self._lock:
            b = self._require(build_id)
            self._ensure_mutable(b)
            if name not in b.milestones:
                raise ForgeError(f"unknown milestone {name!r}")
            b.milestones[name] = True
            return b.manifest()

    def record_artifact(self, build_id: str, name: str, kind: str) -> dict[str, Any]:
        if not _is_str(name):
            raise ForgeError("artifact name must be a non-empty string")
        if kind not in _ARTIFACT_KINDS:
            raise ForgeError(f"artifact kind must be one of {_ARTIFACT_KINDS}")
        with self._lock:
            b = self._require(build_id)
            self._ensure_mutable(b)
            b.artifacts.append({"name": name, "kind": kind})
            return b.manifest()

    def record_tests(self, build_id: str, passed: int, failed: int) -> dict[str, Any]:
        if not isinstance(passed, int) or not isinstance(failed, int) or passed < 0 or failed < 0:
            raise ForgeError("passed/failed must be non-negative ints")
        with self._lock:
            b = self._require(build_id)
            self._ensure_mutable(b)
            b.tests = {"passed": passed, "failed": failed}
            return b.manifest()

    # ── introspection ────────────────────────────────────────────────────────

    def manifest(self, build_id: str) -> dict[str, Any]:
        with self._lock:
            return self._require(build_id).manifest()

    def builds(self) -> list[dict[str, Any]]:
        with self._lock:
            return [b.manifest() for b in self._builds.values()]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_stage: dict[str, int] = {}
            for b in self._builds.values():
                by_stage[b.stage] = by_stage.get(b.stage, 0) + 1
            return {"builds": len(self._builds), "by_stage": by_stage}

    def reset(self) -> None:
        with self._lock:
            self._builds.clear()

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, build_id: str) -> _Build:
        b = self._builds.get(build_id)
        if b is None:
            raise ForgeError(f"unknown build {build_id!r}")
        return b

    @staticmethod
    def _ensure_mutable(b: _Build) -> None:
        """``staged`` is terminal — its manifest must never change afterwards."""
        if b.stage == "staged":
            raise ForgeError(f"build {b.id!r} is staged (terminal) and is immutable")
