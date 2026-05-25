"""MEMORY CITADEL — persistent semantic memory for PRADY OS agents.

Backed by ChromaDB (vector DB) stored in var/memory/.
Each agent owns a scoped collection. Records are queryable by semantic
similarity so ORACLE can retrieve relevant prior outcomes before planning.

Public surface:
    CitadelStore      — primary interface (ChromaDB backend)
    MemoryRecord      — typed record schema
    get_citadel()     — process-level singleton
    InMemoryCitadel   — lightweight stub for testing (no ChromaDB required)
"""

from pradyos.memory_citadel.schema import MemoryRecord, MemoryOutcome
from pradyos.memory_citadel.store import CitadelStore, get_citadel
from pradyos.memory_citadel.inmem import InMemoryCitadel

__all__ = [
    "MemoryRecord",
    "MemoryOutcome",
    "CitadelStore",
    "get_citadel",
    "InMemoryCitadel",
]
