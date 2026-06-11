"""Phase 61C — 20 tests for pradyos.core.tag_index.TagIndex."""
from __future__ import annotations

import pytest

from pradyos.core.tag_index import TagIndex


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_empty():
    t = TagIndex()
    assert t.list_tags() == []


# ── tag / items / tags ───────────────────────────────────────────────────────

def test_tag_adds_item_to_tag_set():
    t = TagIndex()
    t.tag("item1", "red")
    assert "item1" in t.items("red")


def test_tag_idempotent_same_item_same_tag():
    t = TagIndex()
    t.tag("item1", "red")
    t.tag("item1", "red")
    t.tag("item1", "red")
    assert t.items("red") == ["item1"]  # only one entry


def test_items_returns_sorted_list():
    t = TagIndex()
    t.tag("zzz", "color")
    t.tag("aaa", "color")
    t.tag("mmm", "color")
    assert t.items("color") == ["aaa", "mmm", "zzz"]


def test_items_unknown_tag_returns_empty():
    t = TagIndex()
    assert t.items("phantom") == []


def test_tags_returns_sorted_list_for_item():
    t = TagIndex()
    t.tag("item1", "red", "small", "active")
    assert t.tags("item1") == ["active", "red", "small"]


def test_tags_unknown_item_returns_empty():
    t = TagIndex()
    t.tag("other", "x")
    assert t.tags("missing") == []


# ── untag ─────────────────────────────────────────────────────────────────────

def test_untag_removes_item_from_tag():
    t = TagIndex()
    t.tag("item1", "red")
    t.untag("item1", "red")
    assert "item1" not in t.items("red")


def test_untag_noop_on_item_not_in_tag():
    t = TagIndex()
    t.tag("other", "red")
    t.untag("missing", "red")  # should not raise
    assert "other" in t.items("red")


def test_untag_removes_empty_tag_set_from_dict():
    t = TagIndex()
    t.tag("item1", "red")
    t.untag("item1", "red")
    # red bucket is now empty → removed from dict → not in list_tags
    assert all(entry["tag"] != "red" for entry in t.list_tags())


# ── delete_item ──────────────────────────────────────────────────────────────

def test_delete_item_removes_from_all_tags_returns_true():
    t = TagIndex()
    t.tag("item1", "red", "blue", "active")
    t.tag("other", "red")
    assert t.delete_item("item1") is True
    assert t.items("red") == ["other"]
    assert t.items("blue") == []
    assert t.tags("item1") == []


def test_delete_item_unknown_returns_false():
    t = TagIndex()
    t.tag("other", "red")
    assert t.delete_item("phantom") is False


def test_delete_item_cleans_up_empty_tag_sets():
    t = TagIndex()
    t.tag("only", "red")
    t.delete_item("only")
    assert all(entry["tag"] != "red" for entry in t.list_tags())


# ── search ───────────────────────────────────────────────────────────────────

def test_search_all_mode_intersection():
    t = TagIndex()
    t.tag("a", "red", "small")
    t.tag("b", "red")
    t.tag("c", "red", "small", "active")
    # Items bearing BOTH red and small: a and c
    assert t.search("red", "small", mode="all") == ["a", "c"]


def test_search_any_mode_union():
    t = TagIndex()
    t.tag("a", "red")
    t.tag("b", "blue")
    t.tag("c", "green")
    assert t.search("red", "blue", mode="any") == ["a", "b"]


def test_search_no_tags_returns_empty():
    t = TagIndex()
    t.tag("a", "red")
    assert t.search(mode="all") == []
    assert t.search(mode="any") == []


# ── list_tags / count ────────────────────────────────────────────────────────

def test_list_tags_returns_correct_counts():
    t = TagIndex()
    t.tag("a", "red")
    t.tag("b", "red")
    t.tag("c", "blue")
    entries = {e["tag"]: e["count"] for e in t.list_tags()}
    assert entries == {"red": 2, "blue": 1}


def test_list_tags_sorted_alphabetically():
    t = TagIndex()
    t.tag("a", "zzz")
    t.tag("a", "aaa")
    t.tag("a", "mmm")
    tags = [e["tag"] for e in t.list_tags()]
    assert tags == ["aaa", "mmm", "zzz"]


def test_count_by_tag_returns_item_count():
    t = TagIndex()
    t.tag("a", "red")
    t.tag("b", "red")
    t.tag("c", "red")
    assert t.count("red") == 3
    assert t.count("phantom") == 0


def test_count_total_unique_items():
    t = TagIndex()
    t.tag("a", "red", "blue", "green")  # 1 unique
    t.tag("b", "red")                    # 2 unique
    t.tag("a", "small")                  # still 2 (a re-tagged)
    assert t.count() == 2
