"""AETHER SHELL experience composer.

``capture_intent`` classifies a Sovereign utterance onto one of the
``SURFACES`` by deterministic keyword routing (no terminal exposure — the
machine owns execution; the Sovereign sees surfaces). ``push_card`` adds a card
to a surface with an ``URGENCIES`` level; ``ack_card`` retires it.
``experience`` composes the governance-chamber view: active cards ordered
urgent-first then oldest-first, grouped by surface, with one calm headline.
"""

from __future__ import annotations

import threading
from typing import Any

SURFACES = ("governance", "projects", "status", "alerts", "gallery")
URGENCIES = ("info", "attention", "urgent")

# Deterministic intent routing: first keyword hit wins (checked in order).
_INTENT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("approve", "governance"),
    ("reject", "governance"),
    ("defer", "governance"),
    ("proposal", "governance"),
    ("build", "projects"),
    ("project", "projects"),
    ("campaign", "projects"),
    ("health", "status"),
    ("status", "status"),
    ("posture", "status"),
    ("alert", "alerts"),
    ("incident", "alerts"),
    ("breach", "alerts"),
    ("artifact", "gallery"),
    ("gallery", "gallery"),
    ("report", "gallery"),
)
_DEFAULT_SURFACE = "projects"  # ambiguity defaults toward project discovery

_URGENCY_RANK = {u: i for i, u in enumerate(URGENCIES)}  # higher = more urgent


class AetherError(RuntimeError):
    """Base class for AETHER SHELL failures."""


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


class AetherShell:
    """Composes the Sovereign experience: intents in, governance cards out."""

    def __init__(self) -> None:
        self._intents: list[dict[str, Any]] = []
        self._cards: dict[str, dict[str, Any]] = {}
        self._seq = 0
        self._lock = threading.RLock()

    # ── intents ──────────────────────────────────────────────────────────────

    def capture_intent(self, intent_id: str, text: str) -> dict[str, Any]:
        """Classify a Sovereign utterance onto a surface (deterministic)."""
        if not _is_str(intent_id):
            raise AetherError("intent_id must be a non-empty string")
        if not _is_str(text):
            raise AetherError("text must be a non-empty string")
        lowered = text.lower()
        surface = _DEFAULT_SURFACE
        for keyword, target in _INTENT_KEYWORDS:
            if keyword in lowered:
                surface = target
                break
        with self._lock:
            self._seq += 1
            intent = {"id": intent_id, "text": text, "surface": surface, "seq": self._seq}
            self._intents.append(intent)
            return dict(intent)

    def intents(self, limit: int = 50) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit <= 0:
            raise AetherError("limit must be a positive integer")
        with self._lock:
            return [dict(i) for i in self._intents[-limit:]]

    # ── cards ────────────────────────────────────────────────────────────────

    def push_card(
        self,
        card_id: str,
        surface: str,
        title: str,
        urgency: str = "info",
        body: str = "",
    ) -> dict[str, Any]:
        if not _is_str(card_id):
            raise AetherError("card_id must be a non-empty string")
        if surface not in SURFACES:
            raise AetherError(f"surface must be one of {SURFACES}")
        if not _is_str(title):
            raise AetherError("title must be a non-empty string")
        if urgency not in URGENCIES:
            raise AetherError(f"urgency must be one of {URGENCIES}")
        with self._lock:
            if card_id in self._cards:
                raise AetherError(f"card {card_id!r} already exists")
            self._seq += 1
            card = {
                "id": card_id,
                "surface": surface,
                "title": title,
                "urgency": urgency,
                "body": body,
                "seq": self._seq,
                "acked": False,
            }
            self._cards[card_id] = card
            return dict(card)

    def ack_card(self, card_id: str) -> dict[str, Any]:
        with self._lock:
            card = self._cards.get(card_id)
            if card is None:
                raise AetherError(f"unknown card {card_id!r}")
            if card["acked"]:
                raise AetherError(f"card {card_id!r} is already acknowledged")
            card["acked"] = True
            return dict(card)

    # ── the composed experience ──────────────────────────────────────────────

    def experience(self) -> dict[str, Any]:
        """The governance-chamber view: urgent-first active cards, per surface."""
        with self._lock:
            active = [dict(c) for c in self._cards.values() if not c["acked"]]
            total_cards = len(self._cards)
        active.sort(key=lambda c: (-_URGENCY_RANK[c["urgency"]], c["seq"]))
        by_surface: dict[str, list[dict[str, Any]]] = {s: [] for s in SURFACES}
        for c in active:
            by_surface[c["surface"]].append(c)
        urgent = sum(1 for c in active if c["urgency"] == "urgent")
        if urgent:
            headline = f"{urgent} matter(s) need the Sovereign's attention"
        elif active:
            headline = f"{len(active)} item(s) awaiting review — no urgency"
        else:
            headline = "All quiet — the machine is governing itself"
        return {
            "headline": headline,
            "active": active,
            "by_surface": {s: cards for s, cards in by_surface.items() if cards},
            "counts": {
                "active": len(active),
                "urgent": urgent,
                "acked": total_cards - len(active),
            },
        }

    # ── introspection ────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            active = sum(1 for c in self._cards.values() if not c["acked"])
            return {
                "intents": len(self._intents),
                "cards": len(self._cards),
                "active_cards": active,
            }

    def reset(self) -> None:
        with self._lock:
            self._intents.clear()
            self._cards.clear()
            self._seq = 0
