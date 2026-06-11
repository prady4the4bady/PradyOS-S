"""Phase 18A — Sovereign Event Ledger.

Append-only, cryptographically chained audit log.  Every entry commits its
content hash into the *next* entry's ``prev_hash``, forming an immutable
chain that can be verified in O(n) time without any external state.

Thread-safety
-------------
``EventLedger.append()`` and ``clear()`` acquire an internal
``threading.Lock`` before mutating the deque so the ledger is safe to call
from multiple threads (e.g. web handlers + background workers) concurrently.
"""

from __future__ import annotations

import collections
import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# LedgerEntry
# ---------------------------------------------------------------------------


@dataclass
class LedgerEntry:
    """One record in the sovereign event ledger."""

    entry_id: str
    prev_hash: str
    entry_hash: str
    service: str
    event: str
    payload: dict
    ts: float

    def to_dict(self) -> dict:
        """Return a plain-dict representation suitable for JSON encoding."""
        return {
            "entry_id": self.entry_id,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "service": self.service,
            "event": self.event,
            "payload": self.payload,
            "ts": self.ts,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_GENESIS_PREV_HASH: str = "0" * 64


def _compute_hash(
    entry_id: str,
    prev_hash: str,
    service: str,
    event: str,
    payload: dict,
    ts: float,
) -> str:
    """Return the SHA-256 hex digest for a ledger entry."""
    raw = entry_id + prev_hash + service + event + json.dumps(payload, sort_keys=True) + str(ts)
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# EventLedger
# ---------------------------------------------------------------------------


class EventLedger:
    """Thread-safe append-only hash-chain ledger.

    Parameters
    ----------
    maxlen:
        Maximum number of entries retained in memory.  Defaults to 1 000.
    """

    def __init__(self, maxlen: int = 1000) -> None:
        self._entries: collections.deque[LedgerEntry] = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(
        self,
        service: str,
        event: str,
        payload: dict | None = None,
    ) -> LedgerEntry:
        """Append a new event record and return it."""
        if payload is None:
            payload = {}

        ts = time.time()
        entry_id = uuid.uuid4().hex

        with self._lock:
            prev_hash = self._entries[-1].entry_hash if self._entries else _GENESIS_PREV_HASH
            entry_hash = _compute_hash(entry_id, prev_hash, service, event, payload, ts)
            entry = LedgerEntry(
                entry_id=entry_id,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                service=service,
                event=event,
                payload=payload,
                ts=ts,
            )
            self._entries.append(entry)

        return entry

    def verify(self) -> bool:
        """Verify the integrity of the entire chain.

        Returns True if intact (or empty), False on any tampering.
        """
        with self._lock:
            entries = list(self._entries)

        if not entries:
            return True

        expected_prev = _GENESIS_PREV_HASH
        for entry in entries:
            if entry.prev_hash != expected_prev:
                return False
            recomputed = _compute_hash(
                entry.entry_id,
                entry.prev_hash,
                entry.service,
                entry.event,
                entry.payload,
                entry.ts,
            )
            if recomputed != entry.entry_hash:
                return False
            expected_prev = entry.entry_hash

        return True

    def get_entries(
        self,
        limit: int = 100,
        service: str | None = None,
        event: str | None = None,
    ) -> list[LedgerEntry]:
        """Return entries most-recent first, with optional filters."""
        with self._lock:
            entries = list(self._entries)

        # Reverse so most-recent is first
        entries.reverse()

        if service is not None:
            entries = [e for e in entries if e.service == service]
        if event is not None:
            entries = [e for e in entries if e.event == event]

        return entries[:limit]

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        """Remove all entries from the ledger."""
        with self._lock:
            self._entries.clear()
