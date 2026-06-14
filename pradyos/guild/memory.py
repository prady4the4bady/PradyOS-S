"""GUILD memory — continual learning across projects.

The first real step toward agents that *get better with experience*:
recall-before-act, store-after. The guild remembers what it produced on past
objectives, and surfaces the relevant ones onto the blackboard before it starts
a new one — so the team builds on its own history instead of starting cold every
time.

Deterministic and side-effect-free: recall is a pure term-overlap ranking over
stored experiences, so it is unit-tested against hand-computed ground truth. The
store is injected into :class:`~pradyos.guild.org.GuildOrg`; ``memory_tool``
exposes recall as a normal guild Tool (so a role reasons over real past work, the
same way the research tool surfaces live web results).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any

from pradyos.guild.org import GuildError, Tool

_WORD = re.compile(r"[a-z0-9]+")
# A small stop-word set so common words don't dominate the overlap score.
_STOP = frozenset(
    """a an the and or but if then to of in on at by for with from into over under is
    are was were be been being do does did have has had this that these those it its as
    not no you your we our they their how why when where can could should would will""".split()
)


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if len(w) > 1 and w not in _STOP}


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


@dataclass(frozen=True)
class Experience:
    seq: int
    objective: str
    content: str
    tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "objective": self.objective,
            "content": self.content,
            "tags": list(self.tags),
        }


class ExperienceStore:
    """A deterministic long-term memory of what the guild has produced."""

    def __init__(self) -> None:
        self._items: list[Experience] = []
        self._seq = 0
        self._lock = threading.RLock()

    def remember(
        self, objective: str, content: str, tags: tuple[str, ...] | list[str] = ()
    ) -> dict[str, Any]:
        if not _is_str(objective):
            raise GuildError("objective must be a non-empty string")
        if not isinstance(content, str):
            raise GuildError("content must be a string")
        with self._lock:
            self._seq += 1
            exp = Experience(self._seq, objective, content, tuple(tags))
            self._items.append(exp)
            return exp.to_dict()

    def recall(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """The past experiences most relevant to ``query`` (term-overlap, recency)."""
        if not isinstance(limit, int) or limit <= 0:
            raise GuildError("limit must be a positive integer")
        q = _terms(query)
        if not q:
            return []
        with self._lock:
            scored = []
            for e in self._items:
                overlap = len(q & _terms(f"{e.objective} {e.content}"))
                if overlap:
                    scored.append((overlap, e))
        # most overlap first, ties broken by most recent.
        scored.sort(key=lambda se: (-se[0], -se[1].seq))
        return [e.to_dict() for _, e in scored[:limit]]

    def all(self, limit: int = 20) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit <= 0:
            raise GuildError("limit must be a positive integer")
        with self._lock:
            return [e.to_dict() for e in self._items[-limit:]]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"experiences": len(self._items)}

    def reset(self) -> None:
        with self._lock:
            self._items.clear()
            self._seq = 0


def memory_tool(store: Any, limit: int = 3) -> Tool:
    """A GUILD tool that recalls relevant past work onto the blackboard."""

    def _run(objective: str) -> str:
        hits = store.recall(objective, limit=limit)
        if not hits:
            return ""
        lines = [f"- {h['objective']}: {h['content'].strip()[:140]}" for h in hits]
        return "Relevant past work by this team:\n" + "\n".join(lines)

    return Tool("memory", "recall relevant past work the team has already done", _run)
