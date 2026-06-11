"""Memory Citadel record schema."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pradyos.core.ids import new_id


class MemoryOutcome(str, Enum):
    """Outcome classification for a stored memory."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    ESCALATED = "escalated"
    UNKNOWN = "unknown"


@dataclass
class MemoryRecord:
    """A single memory entry stored in the Citadel.

    Fields:
        record_id   — unique ID (generated if absent)
        agent_id    — agent that produced this memory (oracle, imperium, titan)
        collection  — ChromaDB collection name (usually == agent_id)
        summary     — human-readable one-line summary (also the embedding text)
        outcome     — MemoryOutcome classification
        payload     — arbitrary structured data (plan, result, error, etc.)
        tags        — free-form labels for filtering
        task_id     — associated IMPERIUM task ID (optional)
        created_at  — Unix timestamp
    """

    summary: str
    agent_id: str = "system"
    collection: str = "system"
    outcome: MemoryOutcome = MemoryOutcome.UNKNOWN
    payload: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    task_id: str | None = None
    record_id: str = field(default_factory=lambda: new_id("mem"))
    created_at: float = field(default_factory=time.time)

    def to_metadata(self) -> dict[str, Any]:
        """Flatten to a ChromaDB-compatible metadata dict (str values only)."""
        return {
            "record_id": self.record_id,
            "agent_id": self.agent_id,
            "collection": self.collection,
            "outcome": self.outcome.value,
            "task_id": self.task_id or "",
            "tags": ",".join(self.tags),
            "created_at": str(self.created_at),
            # Compact payload for metadata — full data is in document
        }

    def to_document(self) -> str:
        """Text representation for embedding. Combines summary + payload keys."""
        extras: list[str] = []
        for k, v in self.payload.items():
            if isinstance(v, str):
                extras.append(f"{k}: {v}")
        return self.summary + (" | " + " | ".join(extras) if extras else "")

    @classmethod
    def from_query_result(cls, doc: str, metadata: dict[str, Any]) -> MemoryRecord:
        """Reconstruct a MemoryRecord from a ChromaDB query hit."""
        try:
            outcome = MemoryOutcome(metadata.get("outcome", "unknown"))
        except ValueError:
            outcome = MemoryOutcome.UNKNOWN
        return cls(
            summary=doc,
            record_id=metadata.get("record_id", ""),
            agent_id=metadata.get("agent_id", ""),
            collection=metadata.get("collection", ""),
            outcome=outcome,
            task_id=metadata.get("task_id") or None,
            tags=metadata.get("tags", "").split(",") if metadata.get("tags") else [],
            created_at=float(metadata.get("created_at", 0) or 0),
        )
