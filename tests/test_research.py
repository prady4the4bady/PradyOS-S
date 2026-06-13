"""RESEARCH engine tests — orchestration verified deterministically vs fakes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pradyos.research import (
    ResearchEngine,
    ResearchError,
    RssSource,
    SourceDoc,
    WebAgentSource,
    strip_html,
)

_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Tech</title>
  <item><title>Rust async runtimes compared</title><link>https://ex.com/rust</link>
    <description>A look at tokio and async-std.</description></item>
  <item><title>Bread recipes</title><link>https://ex.com/bread</link>
    <description>sourdough tips</description></item>
</channel></rss>"""

_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Python typing news</title><link href="https://ex.com/typing"/>
    <summary>PEP updates for typing.</summary></entry>
</feed>"""


class FakeSource:
    """A deterministic source: canned docs, optionally keyed by query."""

    def __init__(self, name, docs=None, docs_by_query=None, fail_on=None):
        self.name = name
        self._docs = docs
        self._by_query = docs_by_query or {}
        self._fail_on = fail_on

    def search(self, query, limit):
        if self._fail_on is not None and self._fail_on in query:
            raise RuntimeError("source exploded")
        docs = self._docs if self._docs is not None else self._by_query.get(query, [])
        return list(docs)[:limit]


def _doc(url, title, snippet="", content="", source=""):
    return SourceDoc(url=url, title=title, snippet=snippet, content=content, source=source)


# ── sources / registration ───────────────────────────────────────────────────


def test_register_and_list_sources():
    eng = ResearchEngine()
    assert eng.sources() == []
    eng.register_source(FakeSource("web"))
    eng.register_source(FakeSource("forum"))
    assert eng.sources() == ["forum", "web"]


def test_register_invalid_source_raises():
    eng = ResearchEngine()
    with pytest.raises(ResearchError):
        eng.register_source(SimpleNamespace(name="", search=lambda q, n: []))
    with pytest.raises(ResearchError):
        eng.register_source(SimpleNamespace(name="x"))  # no search


def test_constructor_validation():
    with pytest.raises(ResearchError):
        ResearchEngine(max_results_per_query=0)


# ── query planning ────────────────────────────────────────────────────────────


def test_plan_queries_default_angles():
    eng = ResearchEngine()
    qs = eng.plan_queries("python web")
    assert qs == [
        "python web",
        "python web overview",
        "python web comparison",
        "python web best practices",
    ]


def test_plan_queries_dedupes_and_custom_angles():
    eng = ResearchEngine()
    assert eng.plan_queries("topic", angles=()) == ["topic"]
    # duplicate angle collapses
    assert eng.plan_queries("x", angles=("a", "a")) == ["x", "x a"]


def test_plan_queries_validation():
    with pytest.raises(ResearchError):
        ResearchEngine().plan_queries("   ")


# ── ranking / dedup ───────────────────────────────────────────────────────────


def test_research_ranks_by_term_overlap():
    docs = [
        _doc("https://a.com/x", "Cooking recipes", "best pasta sauce"),  # score 0
        _doc("https://b.com/y", "Django overview", "django is a python web framework"),  # 2
        _doc(
            "https://c.com/z",
            "Python async web frameworks compared",
            "fastapi and aiohttp are async python web frameworks",
        ),  # 4
    ]
    eng = ResearchEngine(sources=[FakeSource("web", docs=docs)])
    brief = eng.research("python async web frameworks", angles=())
    urls = [f["url"] for f in brief.to_dict()["findings"]]
    assert urls == ["https://c.com/z", "https://b.com/y", "https://a.com/x"]
    scores = [f["score"] for f in brief.to_dict()["findings"]]
    assert scores == [4, 2, 0]


def test_research_dedupes_by_url_keeping_higher_score():
    docs = [
        _doc("https://x.com/p", "weak", "python"),  # score 1
        _doc("https://x.com/p/", "python web frameworks", "python web frameworks"),  # 3, same url
    ]
    eng = ResearchEngine(sources=[FakeSource("web", docs=docs)])
    brief = eng.research("python web frameworks", angles=())
    findings = brief.to_dict()["findings"]
    assert len(findings) == 1
    assert findings[0]["score"] == 3 and findings[0]["title"] == "python web frameworks"


def test_research_max_findings_caps_results():
    docs = [_doc(f"https://s{i}.com/", f"python doc {i}", "python") for i in range(8)]
    eng = ResearchEngine(sources=[FakeSource("web", docs=docs)])
    brief = eng.research("python", angles=(), max_findings=3)
    assert len(brief.findings) == 3


def test_findings_record_source_and_domain():
    docs = [_doc("https://www.example.com/a", "python guide", "python guide", source="")]
    eng = ResearchEngine(sources=[FakeSource("web", docs=docs)])
    f = eng.research("python guide", angles=()).findings[0]
    assert f.source == "web" and f.domain == "example.com"


# ── key points / confidence ───────────────────────────────────────────────────


def test_key_points_are_overlapping_sentences():
    content = (
        "FastAPI is a modern async python web framework. "
        "It is built on Starlette and Pydantic. "
        "The weather today is sunny and warm."
    )
    docs = [_doc("https://c.com/z", "async python web framework", content=content)]
    eng = ResearchEngine(sources=[FakeSource("web", docs=docs)])
    kp = eng.research("async python web framework", angles=()).key_points
    assert any("FastAPI" in p for p in kp)
    assert not any("weather" in p for p in kp)  # zero-overlap sentence excluded


def test_confidence_high_with_three_corroborating_domains():
    docs = [
        _doc("https://a.com/", "python web frameworks", "python web frameworks"),  # 3
        _doc("https://b.com/", "python web frameworks", "python web frameworks"),  # 3
        _doc("https://c.com/", "python web frameworks", "python web frameworks"),  # 3
    ]
    eng = ResearchEngine(sources=[FakeSource("web", docs=docs)])
    assert eng.research("python web frameworks", angles=()).confidence == "high"


def test_confidence_low_when_no_sources():
    eng = ResearchEngine()
    brief = eng.research("anything", angles=())
    assert brief.confidence == "low"
    assert brief.findings == ()
    assert any("no research sources" in n for n in brief.notes)
    assert brief.sources_consulted == ()


# ── robustness / self-healing ─────────────────────────────────────────────────


def test_failing_source_is_noted_but_others_survive():
    good = FakeSource("good", docs=[_doc("https://g.com/", "python", "python")])
    bad = FakeSource("bad", fail_on="python")
    eng = ResearchEngine(sources=[good, bad])
    brief = eng.research("python", angles=())
    assert [f["url"] for f in brief.to_dict()["findings"]] == ["https://g.com/"]
    assert any("bad" in n and "failed" in n for n in brief.notes)


def test_unknown_provider_raises():
    eng = ResearchEngine(sources=[FakeSource("web")])
    with pytest.raises(ResearchError):
        eng.research("q", providers=["ghost"], angles=())


def test_research_validation():
    eng = ResearchEngine()
    with pytest.raises(ResearchError):
        eng.research("   ")
    with pytest.raises(ResearchError):
        eng.research("q", max_findings=0, angles=())
    with pytest.raises(ResearchError):
        eng.research("q", max_results_per_query=0, angles=())


# ── briefs / stats / reset ─────────────────────────────────────────────────────


def test_brief_retrieval_and_briefs_and_reset():
    eng = ResearchEngine(
        sources=[FakeSource("web", docs=[_doc("https://a.com/", "python", "python")])]
    )
    b1 = eng.research("python", angles=())
    b2 = eng.research("python again", angles=())
    assert b1.seq == 1 and b2.seq == 2
    assert eng.brief(1)["question"] == "python"
    assert len(eng.briefs()) == 2
    assert eng.stats()["briefs"] == 2 and eng.stats()["sources"] == ["web"]
    with pytest.raises(ResearchError):
        eng.brief(999)
    eng.reset()
    assert eng.stats()["briefs"] == 0
    assert eng.research("fresh", angles=()).seq == 1


def test_sourcedoc_validation():
    with pytest.raises(ResearchError):
        SourceDoc(url="", title="x")


# ── WebAgentSource adapter (no live I/O — fake WebAgent) ───────────────────────


def test_web_agent_source_adapter_maps_results():
    class FakeWebAgent:
        def search(self, query, max_results):
            return [
                SimpleNamespace(
                    url="https://ok.com/",
                    error="",
                    status_code=200,
                    body_text="<html><head><title>OK Page</title></head>"
                    "<body><p>python web frameworks rule</p></body></html>",
                ),
                SimpleNamespace(
                    url="https://bad.com/", error="timeout", status_code=0, body_text=""
                ),
                SimpleNamespace(url="https://e.com/", error="", status_code=500, body_text="oops"),
            ]

    src = WebAgentSource(web_agent=FakeWebAgent())
    docs = src.search("python web frameworks", 5)
    assert len(docs) == 1
    assert docs[0].url == "https://ok.com/" and docs[0].title == "OK Page"
    assert "python web frameworks rule" in docs[0].content
    assert docs[0].source == "web"


def test_strip_html():
    assert strip_html("<p>hello <b>world</b></p>") == "hello world"


# ── RssSource (no live I/O — fake fetcher) ─────────────────────────────────────


def test_rss_source_parses_rss_and_filters_by_query():
    src = RssSource(feeds=["http://feed"], fetcher=lambda url: _RSS)
    docs = src.search("rust async runtimes", 5)
    assert [d.url for d in docs] == ["https://ex.com/rust"]  # 'Bread recipes' filtered out
    assert docs[0].source == "rss" and "tokio" in docs[0].content


def test_rss_source_parses_atom_link_href():
    src = RssSource(feeds=["http://feed"], fetcher=lambda url: _ATOM)
    docs = src.search("python typing", 5)
    assert docs and docs[0].url == "https://ex.com/typing"


def test_rss_source_no_overlap_returns_empty():
    src = RssSource(feeds=["http://feed"], fetcher=lambda url: _RSS)
    assert src.search("quantum chromodynamics", 5) == []


def test_rss_source_bad_xml_and_dead_feed_are_safe():
    assert RssSource(feeds=["http://feed"], fetcher=lambda url: "not xml").search("rust", 5) == []

    def _boom(url):
        raise RuntimeError("feed down")

    assert RssSource(feeds=["http://feed"], fetcher=_boom).search("rust", 5) == []


def test_rss_source_via_engine():
    eng = ResearchEngine(sources=[RssSource(feeds=["http://feed"], fetcher=lambda url: _RSS)])
    brief = eng.research("rust async runtimes", angles=())
    assert brief.to_dict()["sources_consulted"] == ["rss"]
    assert any("ex.com/rust" in f["url"] for f in brief.to_dict()["findings"])
