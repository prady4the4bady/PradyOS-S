"""Phase 18C — EventLedger unit tests (20 tests).

Tests cover:
  1.  append() returns LedgerEntry with correct service/event
  2.  append() auto-generates entry_id as non-empty str
  3.  append() sets ts to approximately now
  4.  append() first entry has prev_hash == "0"*64
  5.  append() second entry's prev_hash == first entry's entry_hash
  6.  append() entry_hash is 64-char hex string
  7.  append() is deterministic given same inputs (same hash for same data)
  8.  append() with payload stores payload correctly
  9.  append() with None payload stores empty dict
 10.  verify() returns True for empty ledger
 11.  verify() returns True for valid single-entry ledger
 12.  verify() returns True for valid multi-entry ledger
 13.  verify() returns False when entry_hash tampered
 14.  verify() returns False when prev_hash tampered
 15.  get_entries() returns most-recent first
 16.  get_entries(limit=1) returns at most 1 entry
 17.  get_entries(service=X) filters by service
 18.  get_entries(event=X) filters by event
 19.  len() reflects number of appended entries
 20.  clear() resets len to 0
"""
from __future__ import annotations

import time

import pytest

from pradyos.core.ledger import EventLedger, LedgerEntry, _compute_hash, _GENESIS_PREV_HASH


# ===========================================================================
# Test 1: append() returns LedgerEntry with correct service/event
# ===========================================================================

def test_append_returns_ledger_entry_with_correct_service_event():
    ledger = EventLedger()
    entry = ledger.append(service="sovereign", event="task.dispatched")
    assert isinstance(entry, LedgerEntry)
    assert entry.service == "sovereign"
    assert entry.event == "task.dispatched"


# ===========================================================================
# Test 2: append() auto-generates entry_id as non-empty str
# ===========================================================================

def test_append_generates_non_empty_entry_id():
    ledger = EventLedger()
    entry = ledger.append(service="titan", event="op.started")
    assert isinstance(entry.entry_id, str)
    assert len(entry.entry_id) > 0


# ===========================================================================
# Test 3: append() sets ts to approximately now
# ===========================================================================

def test_append_sets_ts_to_approximately_now():
    before = time.time()
    ledger = EventLedger()
    entry = ledger.append(service="imperium", event="kernel.booted")
    after = time.time()
    assert before <= entry.ts <= after


# ===========================================================================
# Test 4: append() first entry has prev_hash == "0"*64
# ===========================================================================

def test_append_first_entry_prev_hash_is_genesis():
    ledger = EventLedger()
    entry = ledger.append(service="sovereign", event="genesis")
    assert entry.prev_hash == "0" * 64


# ===========================================================================
# Test 5: append() second entry's prev_hash == first entry's entry_hash
# ===========================================================================

def test_append_second_entry_prev_hash_equals_first_entry_hash():
    ledger = EventLedger()
    first = ledger.append(service="sovereign", event="first")
    second = ledger.append(service="sovereign", event="second")
    assert second.prev_hash == first.entry_hash


# ===========================================================================
# Test 6: append() entry_hash is 64-char hex string
# ===========================================================================

def test_append_entry_hash_is_64_char_hex():
    ledger = EventLedger()
    entry = ledger.append(service="warden", event="patrol.start")
    assert isinstance(entry.entry_hash, str)
    assert len(entry.entry_hash) == 64
    # Must be valid hex
    int(entry.entry_hash, 16)


# ===========================================================================
# Test 7: append() is deterministic — same inputs produce the same hash
# ===========================================================================

def test_append_deterministic_hash():
    """Given identical inputs, _compute_hash must return the same digest."""
    payload = {"x": 1, "y": 2}
    h1 = _compute_hash("id1", "0" * 64, "sovereign", "test.event", payload, 1234567890.0)
    h2 = _compute_hash("id1", "0" * 64, "sovereign", "test.event", payload, 1234567890.0)
    assert h1 == h2


# ===========================================================================
# Test 8: append() with payload stores payload correctly
# ===========================================================================

def test_append_with_payload_stores_correctly():
    ledger = EventLedger()
    payload = {"campaign_id": "c1", "result": "ok"}
    entry = ledger.append(service="titan", event="campaign.completed", payload=payload)
    assert entry.payload == {"campaign_id": "c1", "result": "ok"}


# ===========================================================================
# Test 9: append() with None payload stores empty dict
# ===========================================================================

def test_append_none_payload_stored_as_empty_dict():
    ledger = EventLedger()
    entry = ledger.append(service="oracle", event="scan.done", payload=None)
    assert entry.payload == {}


# ===========================================================================
# Test 10: verify() returns True for empty ledger
# ===========================================================================

def test_verify_empty_ledger_returns_true():
    ledger = EventLedger()
    assert ledger.verify() is True


# ===========================================================================
# Test 11: verify() returns True for valid single-entry ledger
# ===========================================================================

def test_verify_single_entry_returns_true():
    ledger = EventLedger()
    ledger.append(service="sovereign", event="boot")
    assert ledger.verify() is True


# ===========================================================================
# Test 12: verify() returns True for valid multi-entry ledger
# ===========================================================================

def test_verify_multi_entry_returns_true():
    ledger = EventLedger()
    for i in range(10):
        ledger.append(service="imperium", event=f"step.{i}", payload={"i": i})
    assert ledger.verify() is True


# ===========================================================================
# Test 13: verify() returns False when entry_hash tampered
# ===========================================================================

def test_verify_returns_false_on_tampered_entry_hash():
    ledger = EventLedger()
    ledger.append(service="sovereign", event="boot")
    # Directly mutate the stored entry's hash
    entry = ledger._entries[0]
    object.__setattr__(entry, "entry_hash", "a" * 64)
    assert ledger.verify() is False


# ===========================================================================
# Test 14: verify() returns False when prev_hash tampered
# ===========================================================================

def test_verify_returns_false_on_tampered_prev_hash():
    ledger = EventLedger()
    ledger.append(service="sovereign", event="first")
    ledger.append(service="sovereign", event="second")
    # Tamper the second entry's prev_hash
    second = ledger._entries[1]
    object.__setattr__(second, "prev_hash", "b" * 64)
    assert ledger.verify() is False


# ===========================================================================
# Test 15: get_entries() returns most-recent first
# ===========================================================================

def test_get_entries_most_recent_first():
    ledger = EventLedger()
    ledger.append(service="s", event="first")
    ledger.append(service="s", event="second")
    ledger.append(service="s", event="third")
    entries = ledger.get_entries()
    events = [e.event for e in entries]
    assert events == ["third", "second", "first"]


# ===========================================================================
# Test 16: get_entries(limit=1) returns at most 1 entry
# ===========================================================================

def test_get_entries_limit_respected():
    ledger = EventLedger()
    for i in range(5):
        ledger.append(service="s", event=f"e{i}")
    entries = ledger.get_entries(limit=1)
    assert len(entries) <= 1


# ===========================================================================
# Test 17: get_entries(service=X) filters by service
# ===========================================================================

def test_get_entries_service_filter():
    ledger = EventLedger()
    ledger.append(service="sovereign", event="a")
    ledger.append(service="titan", event="b")
    ledger.append(service="sovereign", event="c")
    entries = ledger.get_entries(service="sovereign")
    assert all(e.service == "sovereign" for e in entries)
    assert len(entries) == 2


# ===========================================================================
# Test 18: get_entries(event=X) filters by event
# ===========================================================================

def test_get_entries_event_filter():
    ledger = EventLedger()
    ledger.append(service="s", event="task.done")
    ledger.append(service="s", event="task.started")
    ledger.append(service="s", event="task.done")
    entries = ledger.get_entries(event="task.done")
    assert all(e.event == "task.done" for e in entries)
    assert len(entries) == 2


# ===========================================================================
# Test 19: len() reflects number of appended entries
# ===========================================================================

def test_len_reflects_appended_count():
    ledger = EventLedger()
    assert len(ledger) == 0
    for i in range(7):
        ledger.append(service="s", event=f"e{i}")
    assert len(ledger) == 7


# ===========================================================================
# Test 20: clear() resets len to 0
# ===========================================================================

def test_clear_resets_len_to_zero():
    ledger = EventLedger()
    for i in range(5):
        ledger.append(service="s", event=f"e{i}")
    assert len(ledger) == 5
    ledger.clear()
    assert len(ledger) == 0
