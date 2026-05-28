"""Phase 46C — 20 tests for pradyos.core.web_agent.WebAgent.

NO real HTTP calls — all urllib.request.urlopen is mocked.
"""
from __future__ import annotations

import io
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from pradyos.core.web_agent import WebAgent, WebResult


# ── mock helpers ──────────────────────────────────────────────────────────────

@contextmanager
def _mock_urlopen(body: bytes = b"<html></html>", status: int = 200,
                  content_type: str = "text/html"):
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.headers = {"Content-Type": content_type}
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp) as m:
        yield m


@contextmanager
def _mock_urlopen_error(exc: Exception):
    with patch("urllib.request.urlopen", side_effect=exc) as m:
        yield m


class _FakeSnapshot:
    def __init__(self, data: dict) -> None:
        self.data = data


class _FakeStore:
    def __init__(self) -> None:
        self.saved: dict[str, dict] = {}
        self.preset: dict[str, _FakeSnapshot] = {}

    def get(self, namespace: str, key: str, version=None):
        return self.preset.get(key)

    def save(self, namespace: str, key: str, data: dict):
        self.saved[key] = data
        return _FakeSnapshot(data)


class _FakeGateApprove:
    def evaluate(self, action, risk_level, context):
        out = MagicMock()
        out.decision = "approved"
        out.reason = ""
        return out


class _FakeGateBlock:
    def evaluate(self, action, risk_level, context):
        out = MagicMock()
        out.decision = "blocked"
        out.reason = "policy_x"
        return out


# ── WebResult ────────────────────────────────────────────────────────────────

def test_webresult_to_dict_has_required_keys():
    r = WebResult(url="x", status_code=200, body_text="b",
                  content_type="t", fetched_at=1.0, error="")
    d = r.to_dict()
    for k in ("url", "status_code", "body_text", "content_type", "fetched_at", "error"):
        assert k in d


# ── init ──────────────────────────────────────────────────────────────────────

def test_init_defaults():
    a = WebAgent()
    s = a.status()
    assert s["cache_enabled"] is False
    assert s["guardrail_enabled"] is False


# ── fetch success ─────────────────────────────────────────────────────────────

def test_fetch_returns_webresult_on_success():
    a = WebAgent()
    with _mock_urlopen(b"hello", status=200):
        r = a.fetch("http://x")
    assert isinstance(r, WebResult)


def test_fetch_status_code_matches_mock():
    a = WebAgent()
    with _mock_urlopen(b"hi", status=200):
        r = a.fetch("http://x")
    assert r.status_code == 200


def test_fetch_body_text_decoded():
    a = WebAgent()
    with _mock_urlopen(b"hello world"):
        r = a.fetch("http://x")
    assert r.body_text == "hello world"


# ── fetch failure ─────────────────────────────────────────────────────────────

def test_fetch_handles_exception():
    a = WebAgent()
    with _mock_urlopen_error(OSError("DNS fail")):
        r = a.fetch("http://x")
    assert r.status_code == 0
    assert "DNS fail" in r.error


# ── cache ─────────────────────────────────────────────────────────────────────

def test_fetch_cache_hit_skips_urlopen():
    store = _FakeStore()
    store.preset["http://x"] = _FakeSnapshot({
        "url": "http://x", "status_code": 200, "body_text": "cached",
        "content_type": "text/html", "fetched_at": time.time(), "error": "",
    })
    a = WebAgent(snapshot_store=store, max_age=3600)
    with patch("urllib.request.urlopen") as m:
        r = a.fetch("http://x")
    m.assert_not_called()
    assert r.body_text == "cached"


def test_fetch_cache_miss_calls_urlopen():
    store = _FakeStore()
    a = WebAgent(snapshot_store=store)
    with _mock_urlopen(b"fresh") as m:
        a.fetch("http://y")
    m.assert_called_once()


def test_fetch_saves_to_cache():
    store = _FakeStore()
    a = WebAgent(snapshot_store=store)
    with _mock_urlopen(b"data"):
        a.fetch("http://x")
    assert "http://x" in store.saved


# ── guardrail ────────────────────────────────────────────────────────────────

def test_fetch_blocked_by_guardrail():
    a = WebAgent(guardrail_gate=_FakeGateBlock())
    with patch("urllib.request.urlopen") as m:
        r = a.fetch("http://x")
    m.assert_not_called()
    assert "blocked" in r.error


def test_fetch_guardrail_approved_proceeds():
    a = WebAgent(guardrail_gate=_FakeGateApprove())
    with _mock_urlopen(b"ok") as m:
        r = a.fetch("http://x")
    m.assert_called_once()
    assert r.body_text == "ok"
    assert r.error == ""


# ── search ───────────────────────────────────────────────────────────────────

def test_search_returns_list():
    a = WebAgent()
    with _mock_urlopen(b"<html></html>"):
        results = a.search("python")
    assert isinstance(results, list)


def test_search_blocked_by_guardrail():
    a = WebAgent(guardrail_gate=_FakeGateBlock())
    results = a.search("anything")
    assert len(results) == 1
    assert "blocked" in results[0].error


def test_search_fetch_failure_returns_error_result():
    a = WebAgent()
    with _mock_urlopen_error(OSError("net down")):
        results = a.search("python")
    assert len(results) == 1
    assert "net down" in results[0].error


def test_search_parses_links_from_html():
    page = (
        b'<html><body>'
        b'<a href="https://example.com/a">A</a>'
        b'<a href="https://other.org/b">B</a>'
        b'</body></html>'
    )
    a = WebAgent()
    # First call returns the search page; subsequent calls return per-link pages.
    call_count = {"n": 0}

    def fake_urlopen(*args, **kwargs):
        call_count["n"] += 1
        resp = MagicMock()
        if call_count["n"] == 1:
            resp.read.return_value = page
        else:
            resp.read.return_value = b"result-page"
        resp.status = 200
        resp.headers = {"Content-Type": "text/html"}
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        results = a.search("python")
    urls = [r.url for r in results]
    assert "https://example.com/a" in urls
    assert "https://other.org/b" in urls


def test_search_max_results_respected():
    page_bytes = b'<html>' + b''.join(
        f'<a href="https://example{i}.com/x">L{i}</a>'.encode()
        for i in range(10)
    ) + b'</html>'

    def fake_urlopen(*args, **kwargs):
        resp = MagicMock()
        resp.read.return_value = page_bytes
        resp.status = 200
        resp.headers = {"Content-Type": "text/html"}
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    a = WebAgent()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        results = a.search("python", max_results=3)
    assert len(results) == 3


def test_search_excludes_engine_domain():
    engine_host_link = b'<a href="https://html.duckduckgo.com/internal">self</a>'
    external_link = b'<a href="https://example.org/page">ext</a>'
    page = b"<html>" + engine_host_link + external_link + b"</html>"

    def fake_urlopen(*args, **kwargs):
        resp = MagicMock()
        resp.read.return_value = page
        resp.status = 200
        resp.headers = {"Content-Type": "text/html"}
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    a = WebAgent()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        results = a.search("python", max_results=10)
    urls = [r.url for r in results]
    assert "https://html.duckduckgo.com/internal" not in urls
    assert "https://example.org/page" in urls


# ── status ───────────────────────────────────────────────────────────────────

def test_status_has_required_keys():
    a = WebAgent()
    s = a.status()
    for k in ("cache_enabled", "guardrail_enabled", "max_age", "timeout"):
        assert k in s


def test_status_cache_enabled_when_store_provided():
    a = WebAgent(snapshot_store=_FakeStore())
    assert a.status()["cache_enabled"] is True


def test_status_guardrail_enabled_when_gate_provided():
    a = WebAgent(guardrail_gate=_FakeGateApprove())
    assert a.status()["guardrail_enabled"] is True
