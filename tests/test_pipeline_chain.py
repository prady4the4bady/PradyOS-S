"""Phase 60C — 20 tests for pradyos.core.pipeline_chain."""
from __future__ import annotations

import pytest

from pradyos.core.pipeline_chain import (
    PipelineChain,
    PipelineRegistry,
    Step,
    StepError,
    delete_field,
    lowercase_field,
    rename_field,
    set_field,
    uppercase_field,
)


# ── StepError ────────────────────────────────────────────────────────────────

def test_step_error_stores_fields():
    exc = StepError("s1", {"a": 1}, "oops")
    assert exc.step_name == "s1"
    assert exc.original_event == {"a": 1}
    assert exc.message == "oops"


# ── transforms ────────────────────────────────────────────────────────────────

def test_set_field_adds_key_to_copy():
    original = {"x": 1}
    result = set_field(original, key="y", value=2)
    assert result == {"x": 1, "y": 2}
    assert original == {"x": 1}  # not mutated


def test_delete_field_removes_key_from_copy():
    original = {"x": 1, "y": 2}
    result = delete_field(original, key="y")
    assert result == {"x": 1}
    assert original == {"x": 1, "y": 2}


def test_rename_field_renames_key_in_copy():
    original = {"old": "v"}
    result = rename_field(original, old="old", new="new")
    assert result == {"new": "v"}
    assert "old" in original  # not mutated


def test_uppercase_field_uppercases_str():
    result = uppercase_field({"name": "hello"}, key="name")
    assert result["name"] == "HELLO"


def test_lowercase_field_lowercases_str():
    result = lowercase_field({"name": "HELLO"}, key="name")
    assert result["name"] == "hello"


def test_uppercase_field_missing_key_raises_step_error():
    with pytest.raises(StepError):
        uppercase_field({"other": "x"}, key="missing")


def test_lowercase_field_non_str_raises_step_error():
    with pytest.raises(StepError):
        lowercase_field({"count": 42}, key="count")


# ── PipelineChain.run ────────────────────────────────────────────────────────

def test_chain_run_single_step():
    chain = PipelineChain(
        name="c1",
        steps=[Step("set_x", "set_field", {"key": "x", "value": 1})],
    )
    assert chain.run({}) == {"x": 1}


def test_chain_run_multi_step_chains_output():
    chain = PipelineChain(
        name="c1",
        steps=[
            Step("set_name", "set_field", {"key": "name", "value": "alice"}),
            Step("upper", "uppercase_field", {"key": "name"}),
        ],
    )
    assert chain.run({}) == {"name": "ALICE"}


def test_chain_run_does_not_mutate_original():
    original = {"x": 1}
    chain = PipelineChain(
        name="c1",
        steps=[Step("set_y", "set_field", {"key": "y", "value": 2})],
    )
    chain.run(original)
    assert original == {"x": 1}  # untouched


def test_chain_run_short_circuits_on_step_error():
    chain = PipelineChain(
        name="c1",
        steps=[
            Step("good", "set_field", {"key": "x", "value": 1}),
            Step("bad", "uppercase_field", {"key": "missing"}),
            Step("after", "set_field", {"key": "z", "value": 3}),  # should not run
        ],
    )
    with pytest.raises(StepError) as exc_info:
        chain.run({})
    assert exc_info.value.step_name == "bad"


def test_chain_run_empty_returns_event_unchanged_copy():
    chain = PipelineChain(name="empty", steps=[])
    result = chain.run({"a": 1})
    assert result == {"a": 1}


# ── PipelineRegistry ─────────────────────────────────────────────────────────

def test_registry_starts_empty():
    r = PipelineRegistry()
    assert r.list_chains() == []


def test_register_and_get_roundtrip():
    r = PipelineRegistry()
    chain = PipelineChain(name="c1", steps=[])
    r.register(chain)
    assert r.get("c1") is chain


def test_register_overwrites_duplicate_name():
    r = PipelineRegistry()
    r.register(PipelineChain(name="c1", steps=[Step("a", "set_field", {"key": "x", "value": 1})]))
    r.register(PipelineChain(name="c1", steps=[Step("b", "set_field", {"key": "y", "value": 2})]))
    chain = r.get("c1")
    assert chain.steps[0].name == "b"


def test_get_unknown_returns_none():
    r = PipelineRegistry()
    assert r.get("phantom") is None


def test_delete_returns_true_removes():
    r = PipelineRegistry()
    r.register(PipelineChain(name="c1", steps=[]))
    assert r.delete("c1") is True
    assert r.get("c1") is None


def test_delete_unknown_returns_false():
    r = PipelineRegistry()
    assert r.delete("phantom") is False


def test_registry_run_unknown_raises_key_error():
    r = PipelineRegistry()
    with pytest.raises(KeyError):
        r.run("phantom", {})


def test_registry_run_propagates_step_error():
    r = PipelineRegistry()
    r.register(PipelineChain(
        name="c1",
        steps=[Step("bad", "uppercase_field", {"key": "missing"})],
    ))
    with pytest.raises(StepError):
        r.run("c1", {})
