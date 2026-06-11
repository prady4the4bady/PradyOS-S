"""Phase 23C — Unit tests for pradyos.core.rate_limiter (20 tests)."""
from __future__ import annotations

import pytest
from pradyos.core.rate_limiter import RateLimiter, RateLimitResult


# ── Helpers ─────────────────────────────────────────────────────────────────

def make_clock(start: float = 1_000_000.0):
    """Returns a stateful fake clock that starts at *start*."""
    state = [start]

    def clock() -> float:
        return state[0]

    def advance(secs: float) -> None:
        state[0] += secs

    return clock, advance


# ── 1. RateLimiter initialises with empty rules ──────────────────────────────

def test_init_empty_rules():
    rl = RateLimiter()
    assert rl.get_rules() == {}


# ── 2. check() returns RateLimitResult ───────────────────────────────────────

def test_check_returns_rate_limit_result():
    rl = RateLimiter(default_limit=10, default_window=60.0)
    result = rl.check("client1", "/api/foo")
    assert isinstance(result, RateLimitResult)


# ── 3. allowed=True when under limit ─────────────────────────────────────────

def test_allowed_when_under_limit():
    rl = RateLimiter(default_limit=5, default_window=60.0)
    result = rl.check("c1", "/ep")
    assert result.allowed is True


# ── 4. allowed=False when at or over limit ───────────────────────────────────

def test_denied_when_at_limit():
    rl = RateLimiter(default_limit=3, default_window=60.0)
    clock, _ = make_clock()
    for _ in range(3):
        rl.check("c1", "/ep", clock=clock)
    result = rl.check("c1", "/ep", clock=clock)
    assert result.allowed is False


# ── 5. check() records hits (count increments) ───────────────────────────────

def test_count_increments():
    rl = RateLimiter(default_limit=10, default_window=60.0)
    clock, _ = make_clock()
    r1 = rl.check("c1", "/ep", clock=clock)
    r2 = rl.check("c1", "/ep", clock=clock)
    assert r1.current == 1
    assert r2.current == 2


# ── 6. check() does NOT record hit when denied ───────────────────────────────

def test_denied_does_not_record_hit():
    rl = RateLimiter(default_limit=2, default_window=60.0)
    clock, _ = make_clock()
    rl.check("c1", "/ep", clock=clock)
    rl.check("c1", "/ep", clock=clock)
    # Both consumed; next two are denied
    r3 = rl.check("c1", "/ep", clock=clock)
    r4 = rl.check("c1", "/ep", clock=clock)
    assert r3.allowed is False
    assert r4.allowed is False
    # current should still be 2 (limit)
    assert r3.current == 2
    assert r4.current == 2


# ── 7. sliding window prunes old timestamps ───────────────────────────────────

def test_sliding_window_prunes_old_timestamps():
    rl = RateLimiter(default_limit=2, default_window=10.0)
    clock, advance = make_clock(start=1_000.0)

    rl.check("c1", "/ep", clock=clock)
    rl.check("c1", "/ep", clock=clock)
    # Limit reached
    r = rl.check("c1", "/ep", clock=clock)
    assert r.allowed is False

    # Advance past the window — old hits expire
    advance(11.0)
    r2 = rl.check("c1", "/ep", clock=clock)
    assert r2.allowed is True


# ── 8. set_rule() overrides defaults for that endpoint ───────────────────────

def test_set_rule_overrides_defaults():
    rl = RateLimiter(default_limit=100, default_window=60.0)
    rl.set_rule("/strict", limit=1, window=60.0)
    clock, _ = make_clock()
    rl.check("c1", "/strict", clock=clock)
    r = rl.check("c1", "/strict", clock=clock)
    assert r.allowed is False
    assert r.limit == 1


# ── 9. get_rules() returns copy (mutation-safe) ───────────────────────────────

def test_get_rules_copy_is_mutation_safe():
    rl = RateLimiter()
    rl.set_rule("/ep", limit=5, window=30.0)
    rules = rl.get_rules()
    rules["/ep"]["limit"] = 9999  # mutate copy
    # Original must be unchanged
    assert rl.get_rules()["/ep"]["limit"] == 5


# ── 10. reset(client_id) clears all hits for that client ─────────────────────

def test_reset_client_clears_all():
    rl = RateLimiter(default_limit=5, default_window=60.0)
    clock, _ = make_clock()
    rl.check("c1", "/ep1", clock=clock)
    rl.check("c1", "/ep2", clock=clock)
    rl.reset("c1")
    # After reset, status should show no hits for c1
    st = rl.status()
    assert st["total_hits"] == 0


# ── 11. reset(client_id, endpoint) clears only that (client, endpoint) ───────

def test_reset_specific_endpoint_only():
    rl = RateLimiter(default_limit=10, default_window=60.0)
    clock, _ = make_clock()
    rl.check("c1", "/ep1", clock=clock)
    rl.check("c1", "/ep2", clock=clock)
    rl.reset("c1", "/ep1")
    st = rl.status()
    # ep1 cleared, ep2 remains
    assert st["total_hits"] == 1


# ── 12. status() returns dict with required keys ──────────────────────────────

def test_status_has_required_keys():
    rl = RateLimiter()
    st = rl.status()
    for key in ("active_clients", "total_hits", "rules", "default_limit", "default_window"):
        assert key in st


# ── 13. status() active_clients reflects active clients ──────────────────────

def test_status_active_clients():
    rl = RateLimiter(default_limit=10, default_window=60.0)
    clock, _ = make_clock()
    assert rl.status()["active_clients"] == 0
    rl.check("alice", "/ep", clock=clock)
    rl.check("bob", "/ep", clock=clock)
    assert rl.status()["active_clients"] == 2


# ── 14. status() total_hits reflects total hit count ─────────────────────────

def test_status_total_hits():
    rl = RateLimiter(default_limit=10, default_window=60.0)
    clock, _ = make_clock()
    rl.check("c1", "/ep", clock=clock)
    rl.check("c1", "/ep", clock=clock)
    rl.check("c2", "/ep", clock=clock)
    assert rl.status()["total_hits"] == 3


# ── 15. to_dict() has all required keys ──────────────────────────────────────

def test_to_dict_has_required_keys():
    rl = RateLimiter(default_limit=10, default_window=60.0)
    result = rl.check("c1", "/ep")
    d = result.to_dict()
    for key in ("allowed", "client_id", "endpoint", "limit", "window_secs",
                "current", "retry_after"):
        assert key in d


# ── 16. retry_after is None when allowed ─────────────────────────────────────

def test_retry_after_none_when_allowed():
    rl = RateLimiter(default_limit=5, default_window=60.0)
    result = rl.check("c1", "/ep")
    assert result.retry_after is None


# ── 17. retry_after is float > 0 when denied ─────────────────────────────────

def test_retry_after_positive_when_denied():
    rl = RateLimiter(default_limit=1, default_window=30.0)
    clock, _ = make_clock()
    rl.check("c1", "/ep", clock=clock)
    result = rl.check("c1", "/ep", clock=clock)
    assert result.allowed is False
    assert isinstance(result.retry_after, float)
    assert result.retry_after > 0.0


# ── 18. 10 hits on same endpoint → 11th denied ───────────────────────────────

def test_tenth_hit_allowed_eleventh_denied():
    rl = RateLimiter(default_limit=10, default_window=60.0)
    clock, _ = make_clock()
    for i in range(10):
        r = rl.check("c1", "/ep", clock=clock)
        assert r.allowed is True, f"Hit {i+1} should be allowed"
    r11 = rl.check("c1", "/ep", clock=clock)
    assert r11.allowed is False


# ── 19. different endpoints tracked independently ─────────────────────────────

def test_different_endpoints_independent():
    rl = RateLimiter(default_limit=1, default_window=60.0)
    clock, _ = make_clock()
    r_a = rl.check("c1", "/ep_a", clock=clock)
    r_b = rl.check("c1", "/ep_b", clock=clock)
    assert r_a.allowed is True
    assert r_b.allowed is True  # different endpoint — fresh counter


# ── 20. different clients tracked independently ───────────────────────────────

def test_different_clients_independent():
    rl = RateLimiter(default_limit=1, default_window=60.0)
    clock, _ = make_clock()
    r_alice = rl.check("alice", "/ep", clock=clock)
    r_bob = rl.check("bob", "/ep", clock=clock)
    assert r_alice.allowed is True
    assert r_bob.allowed is True  # different client — fresh counter
