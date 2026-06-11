"""Phase 22C — MetricsRegistry unit tests (20 tests).

Covers:
 1.  Initialises with 8 pre-registered counters at 0
 2.  get() returns 0.0 for unknown counter
 3.  increment() adds 1.0 by default
 4.  increment() with value=2.5 adds 2.5
 5.  increment() creates counter if absent
 6.  set() sets exact value
 7.  set() creates counter if absent
 8.  get_all() returns dict copy (mutation-safe)
 9.  reset() sets counter to 0.0
10.  render_prometheus() returns non-empty string
11.  render_prometheus() contains "# HELP"
12.  render_prometheus() contains "# TYPE"
13.  render_prometheus() contains all 8 pre-registered metric names
14.  render_prometheus() renders integer values without decimal (e.g. "5")
15.  render_prometheus() renders float values with decimal (e.g. "1.5")
16.  render_prometheus() output is sorted by metric name
17.  render_prometheus() ends with trailing newline
18.  thread safety: 100 concurrent increments yield correct total
19.  increment() on same counter twice accumulates correctly
20.  get_all() after set() reflects new value
"""
from __future__ import annotations

import threading

import pytest

from pradyos.core.metrics_registry import MetricsRegistry

_PRE_REGISTERED = (
    "pradyos_campaigns_run_total",
    "pradyos_tasks_dispatched_total",
    "pradyos_errors_total",
    "pradyos_ledger_entries_total",
    "pradyos_intent_suggestions_total",
    "pradyos_policy_violations_total",
    "pradyos_scheduler_jobs_fired_total",
    "pradyos_config_reloads_total",
)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_init_pre_registered_count() -> None:
    """8 pre-registered counters present at init."""
    reg = MetricsRegistry()
    all_counters = reg.get_all()
    assert len([k for k in all_counters if k in _PRE_REGISTERED]) == 8


def test_init_pre_registered_values_are_zero() -> None:
    """All 8 pre-registered counters initialise to 0.0."""
    reg = MetricsRegistry()
    for name in _PRE_REGISTERED:
        assert reg.get(name) == 0.0


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------

def test_get_unknown_returns_zero() -> None:
    reg = MetricsRegistry()
    assert reg.get("does_not_exist_xyz") == 0.0


# ---------------------------------------------------------------------------
# increment()
# ---------------------------------------------------------------------------

def test_increment_default_adds_one() -> None:
    reg = MetricsRegistry()
    reg.increment("pradyos_errors_total")
    assert reg.get("pradyos_errors_total") == 1.0


def test_increment_custom_value() -> None:
    reg = MetricsRegistry()
    reg.increment("pradyos_errors_total", 2.5)
    assert reg.get("pradyos_errors_total") == 2.5


def test_increment_creates_absent_counter() -> None:
    reg = MetricsRegistry()
    reg.increment("brand_new_counter")
    assert reg.get("brand_new_counter") == 1.0


def test_increment_accumulates() -> None:
    reg = MetricsRegistry()
    reg.increment("pradyos_errors_total")
    reg.increment("pradyos_errors_total")
    assert reg.get("pradyos_errors_total") == 2.0


# ---------------------------------------------------------------------------
# set()
# ---------------------------------------------------------------------------

def test_set_exact_value() -> None:
    reg = MetricsRegistry()
    reg.set("pradyos_campaigns_run_total", 42.0)
    assert reg.get("pradyos_campaigns_run_total") == 42.0


def test_set_creates_absent_counter() -> None:
    reg = MetricsRegistry()
    reg.set("another_new_counter", 7.0)
    assert reg.get("another_new_counter") == 7.0


# ---------------------------------------------------------------------------
# get_all()
# ---------------------------------------------------------------------------

def test_get_all_mutation_safe() -> None:
    reg = MetricsRegistry()
    snapshot = reg.get_all()
    snapshot["pradyos_errors_total"] = 9999.0
    assert reg.get("pradyos_errors_total") == 0.0  # registry unaffected


def test_get_all_after_set_reflects_new_value() -> None:
    reg = MetricsRegistry()
    reg.set("pradyos_ledger_entries_total", 100.0)
    all_c = reg.get_all()
    assert all_c["pradyos_ledger_entries_total"] == 100.0


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

def test_reset_sets_to_zero() -> None:
    reg = MetricsRegistry()
    reg.increment("pradyos_errors_total", 5.0)
    reg.reset("pradyos_errors_total")
    assert reg.get("pradyos_errors_total") == 0.0


# ---------------------------------------------------------------------------
# render_prometheus()
# ---------------------------------------------------------------------------

def test_render_prometheus_non_empty() -> None:
    reg = MetricsRegistry()
    assert reg.render_prometheus() != ""


def test_render_prometheus_contains_help() -> None:
    reg = MetricsRegistry()
    assert "# HELP" in reg.render_prometheus()


def test_render_prometheus_contains_type() -> None:
    reg = MetricsRegistry()
    assert "# TYPE" in reg.render_prometheus()


def test_render_prometheus_contains_all_pre_registered() -> None:
    reg = MetricsRegistry()
    output = reg.render_prometheus()
    for name in _PRE_REGISTERED:
        assert name in output, f"Missing metric: {name}"


def test_render_prometheus_integer_no_decimal() -> None:
    reg = MetricsRegistry()
    reg.set("pradyos_errors_total", 5.0)
    output = reg.render_prometheus()
    # The value line must be "pradyos_errors_total 5" — not "5.0"
    assert "pradyos_errors_total 5\n" in output
    assert "pradyos_errors_total 5.0\n" not in output


def test_render_prometheus_float_has_decimal() -> None:
    reg = MetricsRegistry()
    reg.set("pradyos_errors_total", 1.5)
    output = reg.render_prometheus()
    assert "pradyos_errors_total 1.5\n" in output


def test_render_prometheus_sorted_by_name() -> None:
    reg = MetricsRegistry()
    output = reg.render_prometheus()
    # Extract only the value lines (those not starting with #)
    value_lines = [l for l in output.splitlines() if l and not l.startswith("#")]
    names = [l.split()[0] for l in value_lines]
    assert names == sorted(names)


def test_render_prometheus_trailing_newline() -> None:
    reg = MetricsRegistry()
    assert reg.render_prometheus().endswith("\n")


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_thread_safety_concurrent_increments() -> None:
    """100 threads each increment the same counter once → total must be 100."""
    reg = MetricsRegistry()
    threads = [
        threading.Thread(target=reg.increment, args=("pradyos_errors_total",))
        for _ in range(100)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert reg.get("pradyos_errors_total") == 100.0
