"""RESEARCH plane — autonomous intelligence gathering.

Conducts research over pluggable sources and composes ranked, cited briefs.
See :mod:`pradyos.research.engine`.
"""

from __future__ import annotations

from pradyos.research.engine import (
    Finding,
    ResearchBrief,
    ResearchEngine,
    ResearchError,
    SourceDoc,
    WebAgentSource,
    strip_html,
)

__all__ = [
    "Finding",
    "ResearchBrief",
    "ResearchEngine",
    "ResearchError",
    "SourceDoc",
    "WebAgentSource",
    "strip_html",
]
