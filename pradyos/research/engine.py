"""RESEARCH engine — autonomous intelligence gathering.

The agent's "research" capability: take a question, fan it out across one or
more pluggable **sources**, then deterministically aggregate, de-duplicate,
rank, and summarise the results into a cited :class:`ResearchBrief`.

Design (mirrors the rest of the constellation):

  * The **orchestration is pure and deterministic** — planning sub-queries,
    de-duplicating by URL, term-overlap ranking, extractive key-point
    selection, and confidence scoring are all functions of the documents a
    source returns, so the engine is unit-tested against *fake* sources with
    hand-computed ground truth (no live network in the test path).
  * The **I/O lives behind a source interface**. A source is any object with a
    ``name`` attribute and a ``search(query, limit) -> list[SourceDoc]``
    method. :class:`WebAgentSource` adapts the existing
    ``pradyos.core.web_agent.WebAgent`` (live HTTP + DuckDuckGo) to that
    interface; other platforms (transcripts, forums, code hosts, RSS) can be
    dropped in the same way.
  * **Egress is a Sovereign-boundary concern** (constitution §data-egress), so
    the engine ships with *no* live sources registered by default — reading the
    open web is enabled deliberately by registering a source, and a brief always
    records exactly which sources it consulted for the audit ledger.

A failing source never sinks a brief: its error is captured as a note and the
remaining sources still contribute (self-healing intelligence gathering).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# Small, deterministic English stop-word set — enough to stop common words from
# dominating term-overlap scoring without pulling in a dependency.
_STOPWORDS = frozenset(
    """
    a an the and or but if then else for of to in on at by with from into over under
    is are was were be been being do does did doing have has had having this that these
    those it its as not no yes you your we our they their he she his her i me my mine
    what which who whom how why when where can could should would may might will shall
    about above below up down out off again more most some any all each few other than
    """.split()
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]+")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


class ResearchError(RuntimeError):
    """Base class for RESEARCH failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _terms(text: str) -> list[str]:
    """Lowercase content words (stop-words and 1-char tokens removed)."""
    return [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1]


def _term_set(text: str) -> frozenset[str]:
    return frozenset(_terms(text))


def _normalize_url(url: str) -> str:
    """Canonicalise a URL for de-duplication (scheme/host lowered, no trailing /)."""
    try:
        p = urlparse(url.strip())
    except (ValueError, TypeError):
        return url.strip().lower()
    if not p.scheme and not p.netloc:
        return url.strip().lower()
    host = p.netloc.lower()
    path = p.path.rstrip("/") or ""
    return f"{p.scheme.lower()}://{host}{path}" + (f"?{p.query}" if p.query else "")


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except (ValueError, TypeError):
        return ""
    return host[4:] if host.startswith("www.") else host


def strip_html(html: str) -> str:
    """Best-effort HTML → text (deterministic, dependency-free)."""
    text = _TAG.sub(" ", html)
    return _WS.sub(" ", text).strip()


@dataclass(frozen=True)
class SourceDoc:
    """A single document returned by a source."""

    url: str
    title: str
    snippet: str = ""
    content: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        if not _is_str(self.url):
            raise ResearchError("SourceDoc.url must be a non-empty string")
        if not isinstance(self.title, str):
            raise ResearchError("SourceDoc.title must be a string")


@dataclass(frozen=True)
class Finding:
    """A ranked, de-duplicated document in a brief."""

    url: str
    title: str
    snippet: str
    source: str
    domain: str
    score: int
    matched_terms: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "source": self.source,
            "domain": self.domain,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
        }


@dataclass(frozen=True)
class ResearchBrief:
    """The composed result of a research run."""

    seq: int
    question: str
    sub_queries: tuple[str, ...]
    findings: tuple[Finding, ...]
    key_points: tuple[str, ...]
    sources_consulted: tuple[str, ...]
    domains: tuple[str, ...]
    confidence: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "question": self.question,
            "sub_queries": list(self.sub_queries),
            "findings": [f.to_dict() for f in self.findings],
            "key_points": list(self.key_points),
            "sources_consulted": list(self.sources_consulted),
            "domains": list(self.domains),
            "confidence": self.confidence,
            "notes": list(self.notes),
            "finding_count": len(self.findings),
        }


class ResearchEngine:
    """Orchestrates sources into ranked, cited research briefs."""

    def __init__(
        self,
        sources: list[Any] | None = None,
        default_angles: tuple[str, ...] = ("overview", "comparison", "best practices"),
        max_results_per_query: int = 5,
    ) -> None:
        if not isinstance(max_results_per_query, int) or max_results_per_query <= 0:
            raise ResearchError("max_results_per_query must be a positive integer")
        self._sources: dict[str, Any] = {}
        self._default_angles = tuple(default_angles)
        self._max_results = max_results_per_query
        self._briefs: list[ResearchBrief] = []
        self._seq = 0
        self._lock = threading.RLock()
        for s in sources or []:
            self.register_source(s)

    # ── sources ──────────────────────────────────────────────────────────────

    def register_source(self, source: Any) -> str:
        """Register a source (object with ``.name`` and ``.search(query, limit)``)."""
        name = getattr(source, "name", None)
        if not _is_str(name):
            raise ResearchError("source must expose a non-empty .name")
        if not callable(getattr(source, "search", None)):
            raise ResearchError("source must expose a callable .search(query, limit)")
        with self._lock:
            self._sources[name] = source
        return name

    def sources(self) -> list[str]:
        with self._lock:
            return sorted(self._sources)

    # ── planning ─────────────────────────────────────────────────────────────

    def plan_queries(self, question: str, angles: tuple[str, ...] | None = None) -> list[str]:
        """Expand a question into deterministic, de-duplicated sub-queries."""
        if not _is_str(question):
            raise ResearchError("question must be a non-empty string")
        q = question.strip()
        chosen = self._default_angles if angles is None else tuple(angles)
        out: list[str] = []
        seen: set[str] = set()
        for cand in [q, *[f"{q} {a}".strip() for a in chosen if _is_str(a)]]:
            key = cand.lower()
            if key not in seen:
                seen.add(key)
                out.append(cand)
        return out

    # ── the research run ─────────────────────────────────────────────────────

    def research(
        self,
        question: str,
        *,
        providers: list[str] | None = None,
        angles: tuple[str, ...] | None = None,
        max_results_per_query: int | None = None,
        max_findings: int = 10,
    ) -> ResearchBrief:
        """Conduct research and return a composed, cited :class:`ResearchBrief`."""
        if not _is_str(question):
            raise ResearchError("question must be a non-empty string")
        if not isinstance(max_findings, int) or max_findings <= 0:
            raise ResearchError("max_findings must be a positive integer")
        if max_results_per_query is None:
            limit = self._max_results
        elif not isinstance(max_results_per_query, int) or max_results_per_query <= 0:
            raise ResearchError("max_results_per_query must be a positive integer")
        else:
            limit = max_results_per_query

        with self._lock:
            if providers is None:
                chosen = dict(self._sources)
            else:
                missing = [p for p in providers if p not in self._sources]
                if missing:
                    raise ResearchError(f"unknown source(s): {sorted(missing)}")
                chosen = {p: self._sources[p] for p in providers}

        queries = self.plan_queries(question, angles=angles)
        q_terms = _term_set(question)
        notes: list[str] = []

        if not chosen:
            notes.append(
                "no research sources configured — register a source to gather intelligence"
            )

        # Collect documents (I/O happens here, behind the source interface).
        docs: list[SourceDoc] = []
        for name in sorted(chosen):
            source = chosen[name]
            for q in queries:
                try:
                    found = source.search(q, limit)
                except Exception as exc:  # noqa: BLE001 — a flaky source must not sink the brief
                    notes.append(f"source {name!r} failed on {q!r}: {exc}")
                    continue
                for d in found or []:
                    docs.append(
                        d if d.source else SourceDoc(d.url, d.title, d.snippet, d.content, name)
                    )

        findings = self._rank(docs, q_terms, max_findings)
        key_points = self._key_points(docs, findings, q_terms)
        domains = tuple(sorted({f.domain for f in findings if f.domain}))
        confidence = self._confidence(findings, domains)

        with self._lock:
            self._seq += 1
            brief = ResearchBrief(
                seq=self._seq,
                question=question,
                sub_queries=tuple(queries),
                findings=findings,
                key_points=key_points,
                sources_consulted=tuple(sorted(chosen)),
                domains=domains,
                confidence=confidence,
                notes=tuple(notes),
            )
            self._briefs.append(brief)
        return brief

    # ── ranking / summarisation (pure) ───────────────────────────────────────

    def _rank(
        self, docs: list[SourceDoc], q_terms: frozenset[str], max_findings: int
    ) -> tuple[Finding, ...]:
        """De-duplicate by URL and rank by question-term overlap (deterministic)."""
        best: dict[str, Finding] = {}
        for d in docs:
            key = _normalize_url(d.url)
            haystack = _term_set(
                f"{d.title} {d.title} {d.snippet} {d.content}"
            )  # title weighted ×2
            matched = tuple(sorted(q_terms & haystack))
            score = len(matched)
            prior = best.get(key)
            # Keep the higher-scoring doc per URL; tie-break deterministically on title.
            if prior is None or (score, d.title) > (prior.score, prior.title):
                best[key] = Finding(
                    url=d.url,
                    title=d.title or d.url,
                    snippet=d.snippet,
                    source=d.source,
                    domain=_domain(d.url),
                    score=score,
                    matched_terms=matched,
                )
        ranked = sorted(best.values(), key=lambda f: (-f.score, f.url))
        return tuple(ranked[:max_findings])

    def _key_points(
        self, docs: list[SourceDoc], findings: tuple[Finding, ...], q_terms: frozenset[str]
    ) -> tuple[str, ...]:
        """Extractive summary: the highest term-overlap sentences from top findings."""
        if not q_terms:
            return ()
        top_urls = {_normalize_url(f.url) for f in findings[:5]}
        scored: list[tuple[int, int, str]] = []  # (-score, order, sentence)
        order = 0
        seen: set[str] = set()
        for d in docs:
            if _normalize_url(d.url) not in top_urls:
                continue
            corpus = d.content or d.snippet
            for sent in _SENTENCE_SPLIT.split(corpus):
                s = _WS.sub(" ", sent).strip()
                if len(s) < 25 or len(s) > 320:
                    continue
                norm = s.lower()
                if norm in seen:
                    continue
                seen.add(norm)
                overlap = len(q_terms & _term_set(s))
                if overlap == 0:
                    continue
                scored.append((-overlap, order, s))
                order += 1
        scored.sort()
        return tuple(s for _, _, s in scored[:5])

    @staticmethod
    def _confidence(findings: tuple[Finding, ...], domains: tuple[str, ...]) -> str:
        """Honest heuristic: more independent corroborating domains ⇒ more confidence."""
        strong = sum(1 for f in findings if f.score >= 2)
        if len(domains) >= 3 and strong >= 3:
            return "high"
        if len(domains) >= 2 and strong >= 1:
            return "medium"
        return "low"

    # ── introspection ────────────────────────────────────────────────────────

    def brief(self, seq: int) -> dict[str, Any]:
        with self._lock:
            for b in self._briefs:
                if b.seq == seq:
                    return b.to_dict()
        raise ResearchError(f"unknown brief seq={seq}")

    def briefs(self, limit: int = 20) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit <= 0:
            raise ResearchError("limit must be a positive integer")
        with self._lock:
            return [b.to_dict() for b in self._briefs[-limit:]]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "sources": sorted(self._sources),
                "briefs": len(self._briefs),
                "max_results_per_query": self._max_results,
            }

    def reset(self) -> None:
        with self._lock:
            self._briefs.clear()
            self._seq = 0


class WebAgentSource:
    """Adapts ``pradyos.core.web_agent.WebAgent`` to the source interface.

    Live HTTP + DuckDuckGo search behind the deterministic engine. Constructed
    lazily so importing the engine never requires the network. Reading the open
    web is low-risk, but the WebAgent's own guardrail gate still applies.
    """

    name = "web"

    def __init__(self, web_agent: Any | None = None, snippet_chars: int = 300) -> None:
        if web_agent is None:
            from pradyos.core.web_agent import WebAgent

            web_agent = WebAgent()
        self._agent = web_agent
        self._snippet_chars = snippet_chars

    def search(self, query: str, limit: int) -> list[SourceDoc]:
        results = self._agent.search(query, max_results=limit)
        docs: list[SourceDoc] = []
        for r in results:
            if getattr(r, "error", "") or getattr(r, "status_code", 0) != 200:
                continue
            text = strip_html(getattr(r, "body_text", ""))
            title = self._title(getattr(r, "body_text", "")) or r.url
            docs.append(
                SourceDoc(
                    url=r.url,
                    title=title,
                    snippet=text[: self._snippet_chars],
                    content=text[:4000],
                    source=self.name,
                )
            )
        return docs

    @staticmethod
    def _title(html: str) -> str:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return _WS.sub(" ", m.group(1)).strip() if m else ""


def _parse_feed(xml_text: str) -> list[dict[str, str]]:
    """Parse RSS or Atom XML into ``{title, link, summary}`` items (deterministic)."""
    if not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    def _localtext(elem: Any, name: str) -> str:
        for child in elem:
            if child.tag.split("}")[-1].lower() == name:
                return (child.text or "").strip()
        return ""

    items: list[dict[str, str]] = []
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        if tag == "item":  # RSS
            items.append(
                {
                    "title": _localtext(node, "title"),
                    "link": _localtext(node, "link"),
                    "summary": strip_html(_localtext(node, "description")),
                }
            )
        elif tag == "entry":  # Atom
            link = ""
            for child in node:
                if child.tag.split("}")[-1].lower() == "link":
                    link = child.get("href", "") or _localtext(node, "link")
                    break
            items.append(
                {
                    "title": _localtext(node, "title"),
                    "link": link,
                    "summary": strip_html(
                        _localtext(node, "summary") or _localtext(node, "content")
                    ),
                }
            )
    return [i for i in items if i["link"]]


# Default feeds for the live RSS source — stable, low-risk tech feeds the
# Sovereign can reconfigure. Reading is autonomous; egress still flows through
# the WebAgent guardrail gate.
_DEFAULT_FEEDS: tuple[str, ...] = (
    "https://hnrss.org/frontpage",
    "https://www.python.org/blogs/news/rss/",
)


class RssSource:
    """Monitors RSS/Atom feeds; surfaces items matching the research query.

    The Agent-Reach "feed monitoring" idea behind the deterministic engine: it
    fetches a configured set of feeds and returns the items whose title/summary
    overlap the query. Parsing is pure (stdlib ``xml.etree``); the fetch is
    behind an injectable ``fetcher`` (the live default uses ``WebAgent``), so it
    is unit-tested with canned feed XML and never needs the network in tests.
    """

    name = "rss"

    def __init__(
        self,
        feeds: list[str] | tuple[str, ...] | None = None,
        fetcher: Any | None = None,
        snippet_chars: int = 300,
    ) -> None:
        self._feeds = list(_DEFAULT_FEEDS if feeds is None else feeds)
        self._fetcher = fetcher  # callable(url) -> xml text; None ⇒ live WebAgent
        self._snippet_chars = snippet_chars

    def _fetch(self, url: str) -> str:
        if self._fetcher is not None:
            try:
                return self._fetcher(url) or ""
            except Exception:  # noqa: BLE001 — a dead feed must not sink the source
                return ""
        from pradyos.core.web_agent import WebAgent

        r = WebAgent().fetch(url)
        if getattr(r, "error", "") or getattr(r, "status_code", 0) != 200:
            return ""
        return getattr(r, "body_text", "")

    def search(self, query: str, limit: int) -> list[SourceDoc]:
        terms = _term_set(query)
        docs: list[SourceDoc] = []
        for feed_url in self._feeds:
            for item in _parse_feed(self._fetch(feed_url)):
                haystack = _term_set(f"{item['title']} {item['summary']}")
                if terms and not (terms & haystack):
                    continue
                docs.append(
                    SourceDoc(
                        url=item["link"],
                        title=item["title"] or item["link"],
                        snippet=item["summary"][: self._snippet_chars],
                        content=item["summary"][:4000],
                        source=self.name,
                    )
                )
                if len(docs) >= limit:
                    return docs
        return docs
