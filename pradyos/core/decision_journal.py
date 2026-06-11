"""Phase 28A: Sovereign Decision Journal — append-only JSONL with cryptographic chaining."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DecisionEntry:
    """A single decision record in the sovereign decision journal."""

    entry_id: str
    agent_id: str
    decision_type: str
    rationale: str
    outcome: str
    timestamp: float
    prev_hash: str  # SHA-256 of previous entry's content_hash; "0"*64 for genesis
    content_hash: str  # SHA-256 of canonical JSON of this entry (excluding content_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "agent_id": self.agent_id,
            "decision_type": self.decision_type,
            "rationale": self.rationale,
            "outcome": self.outcome,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "content_hash": self.content_hash,
        }

    @classmethod
    def _compute_content_hash(cls, entry_dict_without_content_hash: dict[str, Any]) -> str:
        """Compute the canonical content hash for an entry dict (no content_hash key)."""
        canonical = json.dumps(
            entry_dict_without_content_hash,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DecisionEntry:
        return cls(
            entry_id=d["entry_id"],
            agent_id=d["agent_id"],
            decision_type=d["decision_type"],
            rationale=d["rationale"],
            outcome=d["outcome"],
            timestamp=float(d["timestamp"]),
            prev_hash=d["prev_hash"],
            content_hash=d["content_hash"],
        )


_GENESIS_HASH = "0" * 64


class DecisionJournal:
    """Append-only, cryptographically chained decision journal.

    Thread-safe via threading.Lock.
    Operates in memory-only mode if *path* is None; otherwise persists to JSONL.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        self._entries: list[DecisionEntry] = []
        self._path: Path | None = Path(path) if path is not None else None

        if self._path is not None and self._path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load existing entries from JSONL file (called during __init__)."""
        assert self._path is not None
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    self._entries.append(DecisionEntry.from_dict(json.loads(line)))

    def _append_to_file(self, entry: DecisionEntry) -> None:
        """Append a single entry to the JSONL file."""
        assert self._path is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict()) + "\n")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        agent_id: str,
        decision_type: str,
        rationale: str,
        outcome: str,
        timestamp: float | None = None,
    ) -> DecisionEntry:
        """Create and store a new decision entry; returns the entry."""
        with self._lock:
            ts = timestamp if timestamp is not None else time.time()
            entry_id = uuid.uuid4().hex

            prev_hash = self._entries[-1].content_hash if self._entries else _GENESIS_HASH

            # Build dict without content_hash to compute the hash
            partial: dict[str, Any] = {
                "entry_id": entry_id,
                "agent_id": agent_id,
                "decision_type": decision_type,
                "rationale": rationale,
                "outcome": outcome,
                "timestamp": ts,
                "prev_hash": prev_hash,
            }
            content_hash = DecisionEntry._compute_content_hash(partial)

            entry = DecisionEntry(
                entry_id=entry_id,
                agent_id=agent_id,
                decision_type=decision_type,
                rationale=rationale,
                outcome=outcome,
                timestamp=ts,
                prev_hash=prev_hash,
                content_hash=content_hash,
            )

            self._entries.append(entry)
            if self._path is not None:
                self._append_to_file(entry)

        return entry

    def get_entries(
        self,
        limit: int | None = None,
        offset: int = 0,
        agent_id: str | None = None,
        decision_type: str | None = None,
    ) -> list[DecisionEntry]:
        """Return entries oldest-first with optional filters and pagination."""
        with self._lock:
            results = list(self._entries)

        if agent_id is not None:
            results = [e for e in results if e.agent_id == agent_id]
        if decision_type is not None:
            results = [e for e in results if e.decision_type == decision_type]

        results = results[offset:]
        if limit is not None:
            results = results[:limit]
        return results

    def verify_chain(self) -> bool:
        """Verify cryptographic chain integrity.

        Walks all entries in order, recomputes content_hash, checks prev_hash linkage.
        Returns True if intact, False if any link is broken.
        """
        with self._lock:
            entries = list(self._entries)

        prev_content_hash = _GENESIS_HASH
        for entry in entries:
            # Recompute content hash
            partial = {
                "entry_id": entry.entry_id,
                "agent_id": entry.agent_id,
                "decision_type": entry.decision_type,
                "rationale": entry.rationale,
                "outcome": entry.outcome,
                "timestamp": entry.timestamp,
                "prev_hash": entry.prev_hash,
            }
            expected_hash = DecisionEntry._compute_content_hash(partial)
            if entry.content_hash != expected_hash:
                return False
            if entry.prev_hash != prev_content_hash:
                return False
            prev_content_hash = entry.content_hash

        return True

    def count(self) -> int:
        """Return total number of recorded entries."""
        with self._lock:
            return len(self._entries)
