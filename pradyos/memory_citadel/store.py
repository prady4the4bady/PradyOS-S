"""CitadelStore — ChromaDB-backed semantic memory.

Stores memories in var/memory/ (Windows-safe pathlib paths).
Each agent gets its own ChromaDB collection.
Uses ChromaDB's default embedding function (all-MiniLM-L6-v2 via ONNX).

Design:
- All public methods have both sync and async variants.
- The ChromaDB client is lazy-initialised on first use.
- If ChromaDB is not installed, all operations gracefully no-op.
- Windows-safe: only pathlib Paths, no hardcoded separators.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from pradyos.memory_citadel.schema import MemoryOutcome, MemoryRecord

log = logging.getLogger("pradyos.memory_citadel")

_VALID_AGENTS = frozenset({"oracle", "imperium", "titan", "campaign", "system"})

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton: "CitadelStore | None" = None
_singleton_lock = threading.Lock()


def get_citadel(persist_dir: Path | None = None) -> "CitadelStore":
    """Return the process-level CitadelStore singleton."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = CitadelStore(persist_dir=persist_dir)
    return _singleton


def reset_citadel_for_tests() -> None:
    global _singleton
    with _singleton_lock:
        _singleton = None


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class CitadelStore:
    """ChromaDB-backed semantic memory store.

    Directory layout (all pathlib, no hardcoded separators):
        <persist_dir>/          ← default: <project_root>/var/memory/
            chroma.sqlite3      ← ChromaDB metadata
            <uuid>/             ← per-collection embedding data
    """

    def __init__(self, persist_dir: Path | None = None) -> None:
        if persist_dir is None:
            # Resolve relative to this file: ../../var/memory
            persist_dir = Path(__file__).parent.parent.parent / "var" / "memory"
        self._persist_dir: Path = persist_dir
        self._lock = threading.Lock()
        self._client: Any = None          # chromadb.PersistentClient
        self._collections: dict[str, Any] = {}
        self._chroma_available: bool | None = None  # None = not yet checked

    # ------------------------------------------------------------------
    # Sync API
    # ------------------------------------------------------------------

    def store(self, agent_id: str, record: "MemoryRecord | dict[str, Any]") -> str | None:
        """Persist a memory record. Returns record_id or None on failure."""
        rec = _ensure_record(agent_id, record)
        if rec is None:
            return None
        col = self._get_collection(rec.collection)
        if col is None:
            return None
        try:
            col.add(
                ids=[rec.record_id],
                documents=[rec.to_document()],
                metadatas=[rec.to_metadata()],
            )
            log.debug("Memory stored: %s in %s", rec.record_id, rec.collection)
            return rec.record_id
        except Exception as e:  # noqa: BLE001
            log.debug("Memory store failed: %s", e)
            return None

    def query(
        self,
        query_text: str,
        agent_id: str = "oracle",
        n_results: int = 5,
        outcome_filter: MemoryOutcome | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to n_results semantically similar memories."""
        col = self._get_collection(agent_id)
        if col is None:
            return []
        try:
            where: dict[str, Any] | None = None
            if outcome_filter is not None:
                where = {"outcome": outcome_filter.value}

            kwargs: dict[str, Any] = {
                "query_texts": [query_text],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where

            results = col.query(**kwargs)
            return _format_results(results)
        except Exception as e:  # noqa: BLE001
            log.debug("Memory query failed: %s", e)
            return []

    def delete_collection(self, agent_id: str) -> None:
        """Delete all memories for an agent (used in tests / reset)."""
        client = self._get_client()
        if client is None:
            return
        try:
            client.delete_collection(name=agent_id)
            with self._lock:
                self._collections.pop(agent_id, None)
        except Exception as e:  # noqa: BLE001
            log.debug("Delete collection %s failed: %s", agent_id, e)

    def count(self, agent_id: str) -> int:
        """Return number of records stored for an agent."""
        col = self._get_collection(agent_id)
        if col is None:
            return 0
        try:
            return col.count()
        except Exception:  # noqa: BLE001
            return 0

    # ------------------------------------------------------------------
    # Async API (wrappers for ORACLE async paths)
    # ------------------------------------------------------------------

    async def store_async(
        self, agent_id: str, record: "MemoryRecord | dict[str, Any]"
    ) -> str | None:
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.store, agent_id, record)

    async def query_async(
        self,
        query_text: str,
        agent_id: str = "oracle",
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.query, query_text, agent_id, n_results)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_chroma_available(self) -> bool:
        if self._chroma_available is not None:
            return self._chroma_available
        try:
            import chromadb  # noqa: F401

            self._chroma_available = True
        except ImportError:
            self._chroma_available = False
            log.warning(
                "chromadb not installed — Memory Citadel running in no-op mode. "
                "Install with: pip install chromadb"
            )
        return self._chroma_available

    def _get_client(self) -> Any | None:
        if not self._is_chroma_available():
            return None
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                import chromadb

                self._persist_dir.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=str(self._persist_dir)
                )
                log.info("Memory Citadel online at %s", self._persist_dir)
            except Exception as e:  # noqa: BLE001
                log.error("ChromaDB init failed: %s", e)
                return None
            return self._client

    def _get_collection(self, name: str) -> Any | None:
        with self._lock:
            if name in self._collections:
                return self._collections[name]

        client = self._get_client()
        if client is None:
            return None

        try:
            col = client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
            with self._lock:
                self._collections[name] = col
            return col
        except Exception as e:  # noqa: BLE001
            log.debug("Collection %s unavailable: %s", name, e)
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_record(
    agent_id: str, record: "MemoryRecord | dict[str, Any]"
) -> "MemoryRecord | None":
    if isinstance(record, MemoryRecord):
        rec = record
    elif isinstance(record, dict):
        rec = MemoryRecord(
            summary=record.get("summary") or record.get("intent") or str(record),
            agent_id=agent_id,
            collection=agent_id,
            outcome=MemoryOutcome(record.get("outcome", "unknown"))
            if record.get("outcome") in [o.value for o in MemoryOutcome]
            else MemoryOutcome.UNKNOWN,
            payload=record,
            task_id=record.get("task_id"),
            tags=record.get("tags", []),
        )
    else:
        return None
    # Ensure collection is scoped to agent
    if not rec.collection:
        rec.collection = agent_id
    return rec


def _format_results(results: Any) -> list[dict[str, Any]]:
    """Convert ChromaDB query results to plain dicts."""
    docs = (results.get("documents") or [[]])[0]
    metas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    out: list[dict[str, Any]] = []
    for doc, meta, dist in zip(docs, metas, distances):
        out.append(
            {
                "summary": doc,
                "outcome": meta.get("outcome", "unknown"),
                "agent_id": meta.get("agent_id", ""),
                "task_id": meta.get("task_id", ""),
                "record_id": meta.get("record_id", ""),
                "distance": dist,
                "tags": meta.get("tags", "").split(",") if meta.get("tags") else [],
            }
        )
    return out
