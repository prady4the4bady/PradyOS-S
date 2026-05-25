"""InMemoryCitadel — lightweight in-process stub for testing.

Provides the same query/store interface as CitadelStore but stores
everything in a plain dict. No ChromaDB required.
Similarity search is naive substring matching (sufficient for unit tests).
"""

from __future__ import annotations

import threading
from typing import Any

from pradyos.memory_citadel.schema import MemoryOutcome, MemoryRecord


class InMemoryCitadel:
    """Drop-in stub for CitadelStore. No external dependencies."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Sync API (matches CitadelStore contract)
    # ------------------------------------------------------------------

    def store(self, agent_id: str, record: "MemoryRecord | dict[str, Any]") -> str | None:
        if isinstance(record, MemoryRecord):
            entry = {
                "record_id": record.record_id,
                "summary": record.summary,
                "outcome": record.outcome.value,
                "task_id": record.task_id or "",
                "agent_id": record.agent_id,
                "tags": record.tags,
                "payload": record.payload,
            }
        else:
            entry = dict(record)
            entry.setdefault("record_id", f"mem_{len(self._store)}")
            entry.setdefault("agent_id", agent_id)

        with self._lock:
            self._store.setdefault(agent_id, []).append(entry)
        return entry.get("record_id")

    def query(
        self,
        query_text: str,
        agent_id: str = "oracle",
        n_results: int = 5,
        outcome_filter: MemoryOutcome | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._store.get(agent_id, []))

        query_lower = query_text.lower()
        scored: list[tuple[int, dict[str, Any]]] = []
        for e in entries:
            summary = str(e.get("summary", "")).lower()
            score = sum(1 for word in query_lower.split() if word in summary)
            if outcome_filter and e.get("outcome") != outcome_filter.value:
                continue
            scored.append((score, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:n_results]]

    def count(self, agent_id: str) -> int:
        with self._lock:
            return len(self._store.get(agent_id, []))

    def delete_collection(self, agent_id: str) -> None:
        with self._lock:
            self._store.pop(agent_id, None)

    def clear_all(self) -> None:
        with self._lock:
            self._store.clear()

    # ------------------------------------------------------------------
    # Async API
    # ------------------------------------------------------------------

    async def store_async(
        self, agent_id: str, record: "MemoryRecord | dict[str, Any]"
    ) -> str | None:
        return self.store(agent_id, record)

    async def query_async(
        self,
        query_text: str,
        agent_id: str = "oracle",
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        return self.query(query_text, agent_id=agent_id, n_results=n_results)
