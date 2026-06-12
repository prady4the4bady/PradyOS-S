"""CHRONICLE SAGE — documentation & institutional memory (Agent 7).

v3.0 blueprint Agent 7. CHRONICLE SAGE keeps the OS's living record: it logs a
deployment note after every deployment, a post-mortem after every self-heal, a
changelog after every improvement cycle, and incident entries as they occur —
then answers "what changed" with a grouped digest. Entries are sequence-stamped
(deterministic, no wall clock) and queryable by type and tag.

Public surface:
    ChronicleSage  — the record: record / entries / digest / latest
    ENTRY_TYPES    — the recognised entry kinds
    ChronicleError — typed failures
"""

from __future__ import annotations

from pradyos.chronicle_sage.sage import ENTRY_TYPES, ChronicleError, ChronicleSage

__all__ = ["ChronicleSage", "ENTRY_TYPES", "ChronicleError"]
