"""Phase 28C: DecisionJournal unit tests (20 tests)."""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

import pytest

from pradyos.core.decision_journal import DecisionEntry, DecisionJournal, _GENESIS_HASH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_journal(tmp_path: Path, use_file: bool = False) -> DecisionJournal:
    if use_file:
        return DecisionJournal(path=tmp_path / "journal.jsonl")
    return DecisionJournal()


def _record(j: DecisionJournal, agent: str = "agent-1", dtype: str = "deploy") -> DecisionEntry:
    return j.record(
        agent_id=agent,
        decision_type=dtype,
        rationale="test rationale",
        outcome="test outcome",
    )


# ---------------------------------------------------------------------------
# 1. DecisionJournal initialises with empty entries
# ---------------------------------------------------------------------------
def test_init_empty() -> None:
    j = DecisionJournal()
    assert j.count() == 0
    assert j.get_entries() == []


# ---------------------------------------------------------------------------
# 2. record() returns DecisionEntry
# ---------------------------------------------------------------------------
def test_record_returns_entry() -> None:
    j = DecisionJournal()
    entry = _record(j)
    assert isinstance(entry, DecisionEntry)


# ---------------------------------------------------------------------------
# 3. record() increments count()
# ---------------------------------------------------------------------------
def test_record_increments_count() -> None:
    j = DecisionJournal()
    assert j.count() == 0
    _record(j)
    assert j.count() == 1
    _record(j)
    assert j.count() == 2


# ---------------------------------------------------------------------------
# 4. first entry has prev_hash == "0" * 64
# ---------------------------------------------------------------------------
def test_genesis_prev_hash() -> None:
    j = DecisionJournal()
    entry = _record(j)
    assert entry.prev_hash == _GENESIS_HASH
    assert entry.prev_hash == "0" * 64


# ---------------------------------------------------------------------------
# 5. second entry prev_hash == first entry content_hash
# ---------------------------------------------------------------------------
def test_chaining_prev_hash() -> None:
    j = DecisionJournal()
    e1 = _record(j)
    e2 = _record(j)
    assert e2.prev_hash == e1.content_hash


# ---------------------------------------------------------------------------
# 6. content_hash is 64-char hex string
# ---------------------------------------------------------------------------
def test_content_hash_format() -> None:
    j = DecisionJournal()
    entry = _record(j)
    assert len(entry.content_hash) == 64
    assert all(c in "0123456789abcdef" for c in entry.content_hash)


# ---------------------------------------------------------------------------
# 7. verify_chain() returns True for fresh journal
# ---------------------------------------------------------------------------
def test_verify_chain_empty() -> None:
    j = DecisionJournal()
    assert j.verify_chain() is True


def test_verify_chain_fresh() -> None:
    j = DecisionJournal()
    for _ in range(5):
        _record(j)
    assert j.verify_chain() is True


# ---------------------------------------------------------------------------
# 8. verify_chain() returns False after tampering with an entry
# ---------------------------------------------------------------------------
def test_verify_chain_tampered() -> None:
    j = DecisionJournal()
    _record(j)
    _record(j)
    # Tamper: mutate the rationale of the first entry directly
    j._entries[0].rationale = "TAMPERED"
    assert j.verify_chain() is False


# ---------------------------------------------------------------------------
# 9. get_entries() returns all entries oldest-first
# ---------------------------------------------------------------------------
def test_get_entries_order() -> None:
    j = DecisionJournal()
    entries = [_record(j) for _ in range(5)]
    result = j.get_entries()
    assert [e.entry_id for e in result] == [e.entry_id for e in entries]


# ---------------------------------------------------------------------------
# 10. get_entries(limit=N) returns at most N entries
# ---------------------------------------------------------------------------
def test_get_entries_limit() -> None:
    j = DecisionJournal()
    for _ in range(10):
        _record(j)
    result = j.get_entries(limit=3)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# 11. get_entries(offset=N) skips first N entries
# ---------------------------------------------------------------------------
def test_get_entries_offset() -> None:
    j = DecisionJournal()
    entries = [_record(j) for _ in range(5)]
    result = j.get_entries(offset=2)
    assert len(result) == 3
    assert result[0].entry_id == entries[2].entry_id


# ---------------------------------------------------------------------------
# 12. get_entries(agent_id=...) filters by agent
# ---------------------------------------------------------------------------
def test_get_entries_filter_agent() -> None:
    j = DecisionJournal()
    _record(j, agent="alpha")
    _record(j, agent="beta")
    _record(j, agent="alpha")
    result = j.get_entries(agent_id="alpha")
    assert len(result) == 2
    assert all(e.agent_id == "alpha" for e in result)


# ---------------------------------------------------------------------------
# 13. get_entries(decision_type=...) filters by type
# ---------------------------------------------------------------------------
def test_get_entries_filter_dtype() -> None:
    j = DecisionJournal()
    _record(j, dtype="deploy")
    _record(j, dtype="rollback")
    _record(j, dtype="deploy")
    result = j.get_entries(decision_type="deploy")
    assert len(result) == 2
    assert all(e.decision_type == "deploy" for e in result)


# ---------------------------------------------------------------------------
# 14. memory-only mode (path=None) works correctly
# ---------------------------------------------------------------------------
def test_memory_only_mode() -> None:
    j = DecisionJournal(path=None)
    _record(j)
    assert j.count() == 1
    assert j.verify_chain() is True


# ---------------------------------------------------------------------------
# 15. file mode persists entries to JSONL
# ---------------------------------------------------------------------------
def test_file_mode_persists(tmp_path: Path) -> None:
    jfile = tmp_path / "journal.jsonl"
    j = DecisionJournal(path=jfile)
    _record(j)
    _record(j)
    assert jfile.exists()
    lines = [l for l in jfile.read_text().splitlines() if l.strip()]
    assert len(lines) == 2
    d = json.loads(lines[0])
    assert "entry_id" in d


# ---------------------------------------------------------------------------
# 16. file mode reloads entries on re-init from same path
# ---------------------------------------------------------------------------
def test_file_mode_reloads(tmp_path: Path) -> None:
    jfile = tmp_path / "journal.jsonl"
    j1 = DecisionJournal(path=jfile)
    e1 = _record(j1)
    e2 = _record(j1)

    j2 = DecisionJournal(path=jfile)
    assert j2.count() == 2
    ids = [e.entry_id for e in j2.get_entries()]
    assert e1.entry_id in ids
    assert e2.entry_id in ids


# ---------------------------------------------------------------------------
# 17. reloaded journal verify_chain() returns True
# ---------------------------------------------------------------------------
def test_reload_verify_chain(tmp_path: Path) -> None:
    jfile = tmp_path / "journal.jsonl"
    j1 = DecisionJournal(path=jfile)
    for _ in range(4):
        _record(j1)

    j2 = DecisionJournal(path=jfile)
    assert j2.verify_chain() is True


# ---------------------------------------------------------------------------
# 18. DecisionEntry.to_dict() has all required keys
# ---------------------------------------------------------------------------
def test_to_dict_keys() -> None:
    j = DecisionJournal()
    entry = _record(j)
    d = entry.to_dict()
    required = {
        "entry_id", "agent_id", "decision_type", "rationale",
        "outcome", "timestamp", "prev_hash", "content_hash",
    }
    assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# 19. thread safety: 50 concurrent record() calls all register
# ---------------------------------------------------------------------------
def test_thread_safety() -> None:
    j = DecisionJournal()
    n = 50

    def _do_record(_: int) -> None:
        j.record(
            agent_id="thread-agent",
            decision_type="concurrent",
            rationale="concurrent test",
            outcome="ok",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(_do_record, range(n)))

    assert j.count() == n


# ---------------------------------------------------------------------------
# 20. count() matches len(get_entries())
# ---------------------------------------------------------------------------
def test_count_matches_get_entries() -> None:
    j = DecisionJournal()
    for _ in range(7):
        _record(j)
    assert j.count() == len(j.get_entries())
