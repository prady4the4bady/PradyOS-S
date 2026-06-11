"""Phase 29A: Sovereign Capability Registry.

A self-describing runtime registry of all PradyOS module capabilities.
Thread-safe. Stdlib only.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class Capability:
    """A single module capability record."""

    name: str
    version: str
    provided_apis: list
    consumed_apis: list
    status: str  # "active" | "inactive" | "degraded"
    registered_at: float
    metadata: dict

    def to_dict(self) -> dict:
        """Serialise to a plain dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "provided_apis": list(self.provided_apis),
            "consumed_apis": list(self.consumed_apis),
            "status": self.status,
            "registered_at": self.registered_at,
            "metadata": dict(self.metadata),
        }


class CapabilityRegistry:
    """Thread-safe runtime registry of PradyOS module capabilities."""

    def __init__(self) -> None:
        self.capabilities: dict = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        version: str,
        provided_apis=None,
        consumed_apis=None,
        status: str = "active",
        metadata=None,
    ):
        """Create or overwrite a capability entry and return it."""
        cap = Capability(
            name=name,
            version=version,
            provided_apis=list(provided_apis) if provided_apis is not None else [],
            consumed_apis=list(consumed_apis) if consumed_apis is not None else [],
            status=status,
            registered_at=time.time(),
            metadata=dict(metadata) if metadata is not None else {},
        )
        with self._lock:
            self.capabilities[name] = cap
        return cap

    def update_status(self, name: str, status: str) -> bool:
        """Update the status of an existing capability.

        Returns True if found and updated, False if the name is unknown.
        """
        with self._lock:
            cap = self.capabilities.get(name)
            if cap is None:
                return False
            cap.status = status
            return True

    def unregister(self, name: str) -> bool:
        """Remove a capability by name.

        Returns True if removed, False if the name was not present.
        """
        with self._lock:
            if name not in self.capabilities:
                return False
            del self.capabilities[name]
            return True

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, name: str):
        """Return the Capability for *name*, or None if not found."""
        with self._lock:
            return self.capabilities.get(name)

    def list_all(self) -> list:
        """Return all capabilities sorted ascending by name."""
        with self._lock:
            return sorted(self.capabilities.values(), key=lambda c: c.name)

    def summary(self) -> dict:
        """Return a high-level summary of the registry.

        Keys:
            total       -- number of registered capabilities
            active      -- count with status == "active"
            inactive    -- count with status == "inactive"
            degraded    -- count with status == "degraded"
            api_surface -- unique entries across all provided_apis lists
        """
        with self._lock:
            caps = list(self.capabilities.values())

        total = len(caps)
        active = sum(1 for c in caps if c.status == "active")
        inactive = sum(1 for c in caps if c.status == "inactive")
        degraded = sum(1 for c in caps if c.status == "degraded")
        all_apis: set = set()
        for c in caps:
            all_apis.update(c.provided_apis)

        return {
            "total": total,
            "active": active,
            "inactive": inactive,
            "degraded": degraded,
            "api_surface": len(all_apis),
        }
