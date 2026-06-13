"""RESEARCH plane — autonomous intelligence gathering.

Conducts research over pluggable sources and composes ranked, cited briefs.
See :mod:`pradyos.research.engine`.
"""

from __future__ import annotations

from pradyos.research.engine import (
    ArxivSource,
    Finding,
    GitHubSource,
    HackerNewsSource,
    ResearchBrief,
    ResearchEngine,
    ResearchError,
    RssSource,
    SourceDoc,
    WebAgentSource,
    strip_html,
)

__all__ = [
    "ArxivSource",
    "Finding",
    "GitHubSource",
    "HackerNewsSource",
    "ResearchBrief",
    "ResearchEngine",
    "ResearchError",
    "RssSource",
    "SourceDoc",
    "WebAgentSource",
    "strip_html",
]
