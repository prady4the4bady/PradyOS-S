"""Phase 75 — unit tests for VectorClock (distributed causality tracker)."""
from __future__ import annotations

import threading

import pytest

from pradyos.core.vectorclock import VectorClock


# ── construction ──────────────────────────────────────────────────────────────

def test_empty_clock():
    vc = VectorClock()
    assert vc.to_dict() == {}
    assert vc.actors() == []


def test_init_with_initial_mapping():
    vc = VectorClock({"A": 1, "B": 2})
    assert vc.to_dict() == {"A": 1, "B": 2}


def test_init_negative_raises():
    with pytest.raises(ValueError):
        VectorClock({"A": -1})


def test_init_non_int_raises():
    with pytest.raises(ValueError):
        VectorClock({"A": "x"})


# ── tick / get ────────────────────────────────────────────────────────────────

def test_tick_increments_and_returns():
    vc = VectorClock()
    assert vc.tick("A") == 1
    assert vc.tick("A") == 2
    assert vc.get("A") == 2


def test_tick_actors_are_independent():
    vc = VectorClock()
    vc.tick("A")
    vc.tick("B")
    vc.tick("B")
    assert vc.get("A") == 1
    assert vc.get("B") == 2


def test_get_unknown_actor_is_zero():
    assert VectorClock().get("ghost") == 0


def test_actors_sorted():
    vc = VectorClock()
    vc.tick("C"); vc.tick("A"); vc.tick("B")
    assert vc.actors() == ["A", "B", "C"]


# ── compare ───────────────────────────────────────────────────────────────────

def test_compare_equal_empty():
    assert VectorClock().compare(VectorClock()) == "equal"


def test_compare_equal_identical():
    assert VectorClock({"A": 1, "B": 2}).compare(VectorClock({"A": 1, "B": 2})) == "equal"


def test_compare_before():
    assert VectorClock({"A": 1}).compare(VectorClock({"A": 2})) == "before"


def test_compare_after():
    assert VectorClock({"A": 2}).compare(VectorClock({"A": 1})) == "after"


def test_compare_concurrent():
    assert VectorClock({"A": 1}).compare(VectorClock({"B": 1})) == "concurrent"


def test_compare_before_with_missing_actor():
    # {A:1} is dominated by {A:1, B:1}
    assert VectorClock({"A": 1}).compare(VectorClock({"A": 1, "B": 1})) == "before"


def test_compare_concurrent_mixed():
    # A leads on actor A, B leads on actor B → neither dominates
    assert VectorClock({"A": 2, "B": 1}).compare(VectorClock({"A": 1, "B": 2})) == "concurrent"


def test_compare_self_is_equal():
    vc = VectorClock({"A": 3})
    assert vc.compare(vc) == "equal"


def test_compare_non_vectorclock_raises():
    with pytest.raises(ValueError):
        VectorClock().compare({"A": 1})  # type: ignore[arg-type]


# ── merge ─────────────────────────────────────────────────────────────────────

def test_merge_element_wise_max():
    a = VectorClock({"A": 1, "B": 3})
    a.merge(VectorClock({"A": 2, "B": 1}))
    assert a.to_dict() == {"A": 2, "B": 3}


def test_merge_adds_new_actors():
    a = VectorClock({"A": 1})
    a.merge(VectorClock({"B": 5}))
    assert a.to_dict() == {"A": 1, "B": 5}


def test_merge_is_commutative():
    a, b = VectorClock({"A": 1, "B": 3}), VectorClock({"A": 2, "B": 1})
    a2, b2 = VectorClock({"A": 1, "B": 3}), VectorClock({"A": 2, "B": 1})
    a.merge(b)
    b2.merge(a2)
    assert a.to_dict() == b2.to_dict()


def test_merge_idempotent():
    a = VectorClock({"A": 1, "B": 2})
    other = VectorClock({"A": 3})
    a.merge(other)
    snapshot = a.to_dict()
    a.merge(other)
    assert a.to_dict() == snapshot


def test_merge_non_vectorclock_raises():
    with pytest.raises(ValueError):
        VectorClock().merge("nope")  # type: ignore[arg-type]


# ── copy / clear / snapshot isolation ─────────────────────────────────────────

def test_copy_is_independent():
    a = VectorClock({"A": 1})
    c = a.copy()
    c.tick("A")
    assert a.get("A") == 1
    assert c.get("A") == 2


def test_to_dict_returns_copy():
    a = VectorClock({"A": 5})
    snap = a.to_dict()
    snap["A"] = 99
    assert a.get("A") == 5


def test_clear_resets():
    a = VectorClock({"A": 1, "B": 2})
    a.clear()
    assert a.to_dict() == {}


def test_stats_keys():
    stats = VectorClock({"A": 1}).stats()
    for key in ("clock", "actors", "actor_count"):
        assert key in stats


# ── causality scenario ────────────────────────────────────────────────────────

def test_message_passing_establishes_happens_before():
    # A has a local event, sends its clock to B; B merges then has its own event.
    a = VectorClock(); a.tick("A")               # {A:1}
    b = VectorClock(); b.merge(a); b.tick("B")    # {A:1, B:1}
    assert a.compare(b) == "before"
    assert b.compare(a) == "after"


def test_independent_events_are_concurrent():
    a = VectorClock(); a.tick("A")
    b = VectorClock(); b.tick("B")
    assert a.compare(b) == "concurrent"


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_ticks_are_exact():
    vc = VectorClock()
    errors: list[Exception] = []

    def worker() -> None:
        try:
            for _ in range(1000):
                vc.tick("shared")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert vc.get("shared") == 10 * 1000  # every tick counted under the lock
