"""CHRONICLE SAGE institutional-memory ledger.

Entries are appended with a monotonically increasing ``seq`` (deterministic, no
wall clock — the caller supplies any real timestamps it wants in ``body``/tags).
``digest`` groups the most recent entries by type with counts, answering the
"what changed" question; ``entries`` filters by type and/or tag.
"""

from __future__ import annotations

import threading
from typing import Any

ENTRY_TYPES = (
    "deployment",
    "post_mortem",
    "changelog",
    "incident",
    "improvement",
    "doc",
)


class ChronicleError(RuntimeError):
    """Base class for CHRONICLE SAGE failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


class ChronicleSage:
    """Append-only institutional-memory ledger with a 'what changed' digest."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._seq = 0
        self._lock = threading.RLock()

    # ── record ───────────────────────────────────────────────────────────────

    def record(
        self,
        entry_type: str,
        title: str,
        body: str = "",
        tags: Any = None,
    ) -> dict[str, Any]:
        if entry_type not in ENTRY_TYPES:
            raise ChronicleError(f"entry_type must be one of {ENTRY_TYPES}")
        if not _is_str(title):
            raise ChronicleError("title must be a non-empty string")
        tag_list = list(tags) if tags is not None else []
        if not all(_is_str(t) for t in tag_list):
            raise ChronicleError("tags must be strings")
        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "type": entry_type,
                "title": title,
                "body": body,
                "tags": tag_list,
            }
            self._entries.append(entry)
            return dict(entry)

    # ── query ────────────────────────────────────────────────────────────────

    def entries(
        self,
        entry_type: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if entry_type is not None and entry_type not in ENTRY_TYPES:
            raise ChronicleError(f"entry_type must be one of {ENTRY_TYPES}")
        with self._lock:
            sel = [
                e
                for e in self._entries
                if (entry_type is None or e["type"] == entry_type)
                and (tag is None or tag in e["tags"])
            ]
        return [dict(e) for e in sel[-limit:]]

    def latest(self, entry_type: str | None = None) -> dict[str, Any] | None:
        sel = self.entries(entry_type=entry_type, limit=len(self._entries) or 1)
        return sel[-1] if sel else None

    def digest(self, limit: int = 20) -> dict[str, Any]:
        """A 'what changed' summary: counts per type + the most recent entries."""
        with self._lock:
            by_type: dict[str, int] = {}
            for e in self._entries:
                by_type[e["type"]] = by_type.get(e["type"], 0) + 1
            recent = [dict(e) for e in self._entries[-limit:]]
        return {
            "total": len(self._entries),
            "by_type": by_type,
            "recent": recent,
        }

    # ── introspection ────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_type: dict[str, int] = {}
            for e in self._entries:
                by_type[e["type"]] = by_type.get(e["type"], 0) + 1
            return {"entries": len(self._entries), "by_type": by_type}

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()
            self._seq = 0
