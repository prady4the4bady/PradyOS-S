"""Tests for MEMORY CITADEL — persistent semantic memory (Phase 2).

Uses InMemoryCitadel throughout so no ChromaDB install is required.
CitadelStore tests that require ChromaDB are skipped if the package
is not installed.
"""
from __future__ import annotations

import pytest

from pradyos.memory_citadel.schema import MemoryOutcome, MemoryRecord
from pradyos.memory_citadel.inmem import InMemoryCitadel


# ---------------------------------------------------------------------------
# MemoryRecord schema tests
# ---------------------------------------------------------------------------

class TestMemoryRecord:
    def test_defaults(self):
        r = MemoryRecord(summary="test")
        assert r.agent_id == "system"
        assert r.outcome == MemoryOutcome.UNKNOWN
        assert r.record_id.startswith("mem_")
        assert r.created_at > 0

    def test_to_metadata_all_string_values(self):
        r = MemoryRecord(
            summary="deployed nginx",
            agent_id="oracle",
            collection="oracle",
            outcome=MemoryOutcome.SUCCESS,
            task_id="tk_abc",
            tags=["deploy", "nginx"],
        )
        meta = r.to_metadata()
        assert all(isinstance(v, str) for v in meta.values()), \
            "All metadata values must be strings for ChromaDB compat"
        assert meta["outcome"] == "success"
        assert meta["task_id"] == "tk_abc"
        assert "deploy" in meta["tags"]

    def test_to_document_includes_payload_strings(self):
        r = MemoryRecord(
            summary="installed htop",
            payload={"command": "winget install htop", "result": "ok"},
        )
        doc = r.to_document()
        assert "installed htop" in doc
        assert "winget install htop" in doc

    def test_from_query_result_roundtrip(self):
        r = MemoryRecord(
            summary="test summary",
            agent_id="titan",
            collection="titan",
            outcome=MemoryOutcome.FAILURE,
            task_id="tk_xyz",
            tags=["tag1"],
        )
        meta = r.to_metadata()
        doc = r.to_document()
        r2 = MemoryRecord.from_query_result(doc, meta)
        assert r2.summary == doc
        assert r2.outcome == MemoryOutcome.FAILURE
        assert r2.task_id == "tk_xyz"

    def test_unknown_outcome_on_invalid_value(self):
        r = MemoryRecord.from_query_result("doc", {"outcome": "bogus_value"})
        assert r.outcome == MemoryOutcome.UNKNOWN


# ---------------------------------------------------------------------------
# InMemoryCitadel tests
# ---------------------------------------------------------------------------

class TestInMemoryCitadel:
    def test_store_and_count(self):
        c = InMemoryCitadel()
        c.store("oracle", {"summary": "task one done", "outcome": "success"})
        c.store("oracle", {"summary": "task two done", "outcome": "success"})
        assert c.count("oracle") == 2

    def test_count_scoped_to_agent(self):
        c = InMemoryCitadel()
        c.store("oracle", {"summary": "oracle record"})
        c.store("titan", {"summary": "titan record"})
        assert c.count("oracle") == 1
        assert c.count("titan") == 1
        assert c.count("imperium") == 0

    def test_store_memory_record_directly(self):
        c = InMemoryCitadel()
        r = MemoryRecord(summary="direct record", agent_id="oracle", outcome=MemoryOutcome.SUCCESS)
        record_id = c.store("oracle", r)
        assert record_id == r.record_id
        assert c.count("oracle") == 1

    def test_query_returns_relevant_results(self):
        c = InMemoryCitadel()
        c.store("oracle", {"summary": "installed nginx web server", "outcome": "success"})
        c.store("oracle", {"summary": "updated python packages", "outcome": "success"})
        c.store("oracle", {"summary": "configured firewall rules", "outcome": "success"})

        results = c.query("nginx web server", agent_id="oracle", n_results=5)
        assert len(results) >= 1
        assert any("nginx" in r.get("summary", "") for r in results)

    def test_query_respects_n_results_limit(self):
        c = InMemoryCitadel()
        for i in range(10):
            c.store("oracle", {"summary": f"task {i} completed", "outcome": "success"})
        results = c.query("task completed", agent_id="oracle", n_results=3)
        assert len(results) <= 3

    def test_query_outcome_filter(self):
        c = InMemoryCitadel()
        c.store("oracle", {"summary": "success task", "outcome": "success"})
        c.store("oracle", {"summary": "failure task", "outcome": "failure"})

        success_results = c.query("task", agent_id="oracle",
                                   outcome_filter=MemoryOutcome.SUCCESS)
        for r in success_results:
            assert r.get("outcome") == "success"

    def test_query_returns_empty_for_unknown_agent(self):
        c = InMemoryCitadel()
        results = c.query("anything", agent_id="nonexistent")
        assert results == []

    def test_delete_collection(self):
        c = InMemoryCitadel()
        c.store("oracle", {"summary": "to be deleted"})
        assert c.count("oracle") == 1
        c.delete_collection("oracle")
        assert c.count("oracle") == 0

    def test_clear_all(self):
        c = InMemoryCitadel()
        c.store("oracle", {"summary": "oracle"})
        c.store("titan", {"summary": "titan"})
        c.clear_all()
        assert c.count("oracle") == 0
        assert c.count("titan") == 0

    @pytest.mark.asyncio
    async def test_store_async(self):
        c = InMemoryCitadel()
        rid = await c.store_async("oracle", {"summary": "async store", "outcome": "success"})
        assert rid is not None
        assert c.count("oracle") == 1

    @pytest.mark.asyncio
    async def test_query_async(self):
        c = InMemoryCitadel()
        c.store("oracle", {"summary": "async query test", "outcome": "success"})
        results = await c.query_async("async query", agent_id="oracle", n_results=5)
        assert isinstance(results, list)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# CitadelStore graceful-no-op when ChromaDB absent
# ---------------------------------------------------------------------------

class TestCitadelStoreNoop:
    """CitadelStore must silently no-op if ChromaDB is not installed."""

    def test_store_returns_none_without_chromadb(self, monkeypatch):
        from pradyos.memory_citadel.store import CitadelStore
        monkeypatch.setattr(CitadelStore, "_is_chroma_available", lambda self: False)
        cs = CitadelStore()
        cs._chroma_available = False  # force no-op path
        result = cs.store("oracle", {"summary": "test"})
        assert result is None

    def test_query_returns_empty_without_chromadb(self, monkeypatch):
        from pradyos.memory_citadel.store import CitadelStore
        cs = CitadelStore()
        cs._chroma_available = False
        results = cs.query("test", agent_id="oracle")
        assert results == []

    def test_count_returns_zero_without_chromadb(self):
        from pradyos.memory_citadel.store import CitadelStore
        cs = CitadelStore()
        cs._chroma_available = False
        assert cs.count("oracle") == 0
