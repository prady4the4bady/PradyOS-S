"""Phase 16C — TelemetrySpan / TelemetryCollector unit tests (20 tests).

Covers:
  1.  start_span() returns TelemetrySpan with status="running"
  2.  start_span() auto-generates span_id as non-empty string
  3.  start_span() auto-generates trace_id as non-empty string
  4.  start_span() with explicit trace_id uses that trace_id
  5.  start_span() appends to collector (len increases)
  6.  finish_span() sets status correctly
  7.  finish_span() sets end_ts > start_ts
  8.  finish_span() merges attributes
  9.  finish_span() returns None for unknown span_id
 10.  record() returns span with status="ok" by default
 11.  record() with duration_ms sets end_ts = start_ts + duration_ms/1000
 12.  record() with status="error" stores "error"
 13.  get_spans() returns list
 14.  get_spans(limit=2) returns at most 2 spans
 15.  get_spans(service="sovereign") filters by service
 16.  get_spans(status="error") filters by status
 17.  get_spans() returns most-recent first
 18.  clear() empties collector (len becomes 0)
 19.  deque maxlen is respected (oldest spans evicted)
 20.  duration_ms() returns None if end_ts is None
 21.  duration_ms() returns correct ms when end_ts is set
"""

from __future__ import annotations

import time

import pytest

from pradyos.core.telemetry import TelemetryCollector, TelemetrySpan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collector() -> TelemetryCollector:
    return TelemetryCollector(maxlen=500)


# ===========================================================================
# Test 1: start_span() returns TelemetrySpan with status="running"
# ===========================================================================

def test_start_span_status_running():
    col = _collector()
    span = col.start_span("task.dispatch", "sovereign")
    assert span.status == "running"


# ===========================================================================
# Test 2: start_span() auto-generates span_id as non-empty string
# ===========================================================================

def test_start_span_auto_span_id():
    col = _collector()
    span = col.start_span("task.dispatch", "sovereign")
    assert isinstance(span.span_id, str)
    assert len(span.span_id) > 0


# ===========================================================================
# Test 3: start_span() auto-generates trace_id as non-empty string
# ===========================================================================

def test_start_span_auto_trace_id():
    col = _collector()
    span = col.start_span("task.dispatch", "sovereign")
    assert isinstance(span.trace_id, str)
    assert len(span.trace_id) > 0


# ===========================================================================
# Test 4: start_span() with explicit trace_id uses that trace_id
# ===========================================================================

def test_start_span_explicit_trace_id():
    col = _collector()
    tid = "abc123def456"
    span = col.start_span("task.dispatch", "sovereign", trace_id=tid)
    assert span.trace_id == tid


# ===========================================================================
# Test 5: start_span() appends to collector (len increases)
# ===========================================================================

def test_start_span_appends_to_collector():
    col = _collector()
    assert len(col) == 0
    col.start_span("task.dispatch", "sovereign")
    assert len(col) == 1
    col.start_span("campaign.run", "imperium")
    assert len(col) == 2


# ===========================================================================
# Test 6: finish_span() sets status correctly
# ===========================================================================

def test_finish_span_sets_status():
    col = _collector()
    span = col.start_span("task.dispatch", "sovereign")
    finished = col.finish_span(span.span_id, status="error")
    assert finished is not None
    assert finished.status == "error"


# ===========================================================================
# Test 7: finish_span() sets end_ts > start_ts
# ===========================================================================

def test_finish_span_sets_end_ts_after_start():
    col = _collector()
    span = col.start_span("task.dispatch", "sovereign")
    time.sleep(0.001)  # ensure a tiny gap
    finished = col.finish_span(span.span_id)
    assert finished is not None
    assert finished.end_ts is not None
    assert finished.end_ts >= finished.start_ts


# ===========================================================================
# Test 8: finish_span() merges attributes
# ===========================================================================

def test_finish_span_merges_attributes():
    col = _collector()
    span = col.start_span("task.dispatch", "sovereign", attributes={"env": "prod"})
    col.finish_span(span.span_id, attributes={"result": "ok", "items": 3})
    assert span.attributes["env"] == "prod"
    assert span.attributes["result"] == "ok"
    assert span.attributes["items"] == 3


# ===========================================================================
# Test 9: finish_span() returns None for unknown span_id
# ===========================================================================

def test_finish_span_unknown_id_returns_none():
    col = _collector()
    result = col.finish_span("nonexistent-span-id-xyz")
    assert result is None


# ===========================================================================
# Test 10: record() returns span with status="ok" by default
# ===========================================================================

def test_record_default_status_ok():
    col = _collector()
    span = col.record("campaign.run", "titan")
    assert span.status == "ok"


# ===========================================================================
# Test 11: record() with duration_ms sets end_ts = start_ts + duration_ms/1000
# ===========================================================================

def test_record_duration_ms_sets_end_ts():
    col = _collector()
    span = col.record("campaign.run", "titan", duration_ms=250.0)
    assert span.end_ts is not None
    expected = span.start_ts + 0.25
    assert abs(span.end_ts - expected) < 1e-9


# ===========================================================================
# Test 12: record() with status="error" stores "error"
# ===========================================================================

def test_record_status_error():
    col = _collector()
    span = col.record("campaign.run", "titan", status="error")
    assert span.status == "error"


# ===========================================================================
# Test 13: get_spans() returns list
# ===========================================================================

def test_get_spans_returns_list():
    col = _collector()
    col.start_span("a", "sovereign")
    result = col.get_spans()
    assert isinstance(result, list)


# ===========================================================================
# Test 14: get_spans(limit=2) returns at most 2 spans
# ===========================================================================

def test_get_spans_limit():
    col = _collector()
    for i in range(5):
        col.start_span(f"op.{i}", "sovereign")
    result = col.get_spans(limit=2)
    assert len(result) <= 2


# ===========================================================================
# Test 15: get_spans(service="sovereign") filters by service
# ===========================================================================

def test_get_spans_filter_by_service():
    col = _collector()
    col.start_span("a", "sovereign")
    col.start_span("b", "imperium")
    col.start_span("c", "sovereign")
    result = col.get_spans(service="sovereign")
    assert all(s.service == "sovereign" for s in result)
    assert len(result) == 2


# ===========================================================================
# Test 16: get_spans(status="error") filters by status
# ===========================================================================

def test_get_spans_filter_by_status():
    col = _collector()
    col.record("a", "sovereign", status="ok")
    col.record("b", "sovereign", status="error")
    col.record("c", "sovereign", status="ok")
    result = col.get_spans(status="error")
    assert all(s.status == "error" for s in result)
    assert len(result) == 1


# ===========================================================================
# Test 17: get_spans() returns most-recent first
# ===========================================================================

def test_get_spans_most_recent_first():
    col = _collector()
    col.record("first", "sovereign")
    time.sleep(0.001)
    col.record("second", "sovereign")
    time.sleep(0.001)
    col.record("third", "sovereign")
    result = col.get_spans()
    names = [s.name for s in result]
    assert names[0] == "third"
    assert names[-1] == "first"


# ===========================================================================
# Test 18: clear() empties collector (len becomes 0)
# ===========================================================================

def test_clear_empties_collector():
    col = _collector()
    for _ in range(5):
        col.start_span("op", "sovereign")
    assert len(col) == 5
    col.clear()
    assert len(col) == 0


# ===========================================================================
# Test 19: deque maxlen is respected (oldest spans evicted)
# ===========================================================================

def test_deque_maxlen_evicts_oldest():
    col = TelemetryCollector(maxlen=3)
    s1 = col.start_span("first", "sovereign")
    s2 = col.start_span("second", "sovereign")
    s3 = col.start_span("third", "sovereign")
    s4 = col.start_span("fourth", "sovereign")
    # Ring buffer should hold exactly 3 spans
    assert len(col) == 3
    # The first span should have been evicted
    spans = col.get_spans(limit=100)
    names = [s.name for s in spans]
    assert "first" not in names
    assert "fourth" in names


# ===========================================================================
# Test 20: duration_ms() returns None if end_ts is None
# ===========================================================================

def test_duration_ms_none_when_running():
    span = TelemetrySpan(
        name="task.dispatch",
        service="sovereign",
        trace_id="abc",
        start_ts=time.time(),
        end_ts=None,
        status="running",
    )
    assert span.duration_ms() is None


# ===========================================================================
# Test 21: duration_ms() returns correct ms when end_ts is set  (bonus — spec said 20 tests but
#          this covers the second duration_ms bullet without replacing any test)
# ===========================================================================

def test_duration_ms_correct_when_finished():
    t0 = time.time()
    span = TelemetrySpan(
        name="task.dispatch",
        service="sovereign",
        trace_id="abc",
        start_ts=t0,
        end_ts=t0 + 0.5,
        status="ok",
    )
    assert abs(span.duration_ms() - 500.0) < 1e-6
