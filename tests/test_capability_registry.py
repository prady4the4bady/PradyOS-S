"""Phase 29C: CapabilityRegistry unit tests (20 tests)."""
from __future__ import annotations

import threading
import time

import pytest

from pradyos.core.capability_registry import Capability, CapabilityRegistry


# ---------------------------------------------------------------------------
# 1. CapabilityRegistry initialises empty
# ---------------------------------------------------------------------------
def test_registry_init_empty() -> None:
    reg = CapabilityRegistry()
    assert reg.capabilities == {}


# ---------------------------------------------------------------------------
# 2. register() returns Capability
# ---------------------------------------------------------------------------
def test_register_returns_capability() -> None:
    reg = CapabilityRegistry()
    cap = reg.register("mod_a", "1.0")
    assert isinstance(cap, Capability)


# ---------------------------------------------------------------------------
# 3. register() stores by name
# ---------------------------------------------------------------------------
def test_register_stores_by_name() -> None:
    reg = CapabilityRegistry()
    reg.register("mod_b", "2.0")
    assert "mod_b" in reg.capabilities


# ---------------------------------------------------------------------------
# 4. get() returns Capability for known name
# ---------------------------------------------------------------------------
def test_get_known_name() -> None:
    reg = CapabilityRegistry()
    reg.register("mod_c", "3.0")
    cap = reg.get("mod_c")
    assert cap is not None
    assert cap.name == "mod_c"


# ---------------------------------------------------------------------------
# 5. get() returns None for unknown name
# ---------------------------------------------------------------------------
def test_get_unknown_returns_none() -> None:
    reg = CapabilityRegistry()
    assert reg.get("no_such_module") is None


# ---------------------------------------------------------------------------
# 6. list_all() returns sorted by name
# ---------------------------------------------------------------------------
def test_list_all_sorted() -> None:
    reg = CapabilityRegistry()
    for name in ["zebra", "alpha", "mango"]:
        reg.register(name, "1.0")
    names = [c.name for c in reg.list_all()]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# 7. list_all() returns all registered capabilities
# ---------------------------------------------------------------------------
def test_list_all_returns_all() -> None:
    reg = CapabilityRegistry()
    for name in ["x", "y", "z"]:
        reg.register(name, "1.0")
    assert len(reg.list_all()) == 3


# ---------------------------------------------------------------------------
# 8. register() overwrites existing capability
# ---------------------------------------------------------------------------
def test_register_overwrites() -> None:
    reg = CapabilityRegistry()
    reg.register("dup", "1.0", status="active")
    reg.register("dup", "2.0", status="inactive")
    cap = reg.get("dup")
    assert cap is not None
    assert cap.version == "2.0"
    assert cap.status == "inactive"
    assert len(reg.list_all()) == 1


# ---------------------------------------------------------------------------
# 9. update_status() returns True and updates status
# ---------------------------------------------------------------------------
def test_update_status_returns_true() -> None:
    reg = CapabilityRegistry()
    reg.register("mod_s", "1.0", status="active")
    result = reg.update_status("mod_s", "degraded")
    assert result is True
    assert reg.get("mod_s").status == "degraded"


# ---------------------------------------------------------------------------
# 10. update_status() returns False for unknown name
# ---------------------------------------------------------------------------
def test_update_status_unknown_returns_false() -> None:
    reg = CapabilityRegistry()
    assert reg.update_status("ghost", "inactive") is False


# ---------------------------------------------------------------------------
# 11. unregister() returns True and removes
# ---------------------------------------------------------------------------
def test_unregister_removes() -> None:
    reg = CapabilityRegistry()
    reg.register("to_remove", "1.0")
    result = reg.unregister("to_remove")
    assert result is True
    assert reg.get("to_remove") is None


# ---------------------------------------------------------------------------
# 12. unregister() returns False for unknown name
# ---------------------------------------------------------------------------
def test_unregister_unknown_returns_false() -> None:
    reg = CapabilityRegistry()
    assert reg.unregister("never_existed") is False


# ---------------------------------------------------------------------------
# 13. summary() returns required keys
# ---------------------------------------------------------------------------
def test_summary_keys() -> None:
    reg = CapabilityRegistry()
    s = reg.summary()
    assert {"total", "active", "inactive", "degraded", "api_surface"} <= set(s.keys())


# ---------------------------------------------------------------------------
# 14. summary() active count correct
# ---------------------------------------------------------------------------
def test_summary_active_count() -> None:
    reg = CapabilityRegistry()
    reg.register("a1", "1.0", status="active")
    reg.register("a2", "1.0", status="active")
    reg.register("i1", "1.0", status="inactive")
    s = reg.summary()
    assert s["active"] == 2
    assert s["inactive"] == 1
    assert s["degraded"] == 0
    assert s["total"] == 3


# ---------------------------------------------------------------------------
# 15. summary() api_surface counts unique provided_apis
# ---------------------------------------------------------------------------
def test_summary_api_surface_unique() -> None:
    reg = CapabilityRegistry()
    reg.register("m1", "1.0", provided_apis=["/a", "/b"])
    reg.register("m2", "1.0", provided_apis=["/c"])
    s = reg.summary()
    assert s["api_surface"] == 3


# ---------------------------------------------------------------------------
# 16. api_surface deduplicates identical paths across capabilities
# ---------------------------------------------------------------------------
def test_api_surface_deduplicates() -> None:
    reg = CapabilityRegistry()
    reg.register("p1", "1.0", provided_apis=["/shared", "/unique1"])
    reg.register("p2", "1.0", provided_apis=["/shared", "/unique2"])
    s = reg.summary()
    # /shared appears twice but must be counted once
    assert s["api_surface"] == 3


# ---------------------------------------------------------------------------
# 17. provided_apis defaults to []
# ---------------------------------------------------------------------------
def test_provided_apis_default_empty() -> None:
    reg = CapabilityRegistry()
    cap = reg.register("no_apis", "1.0")
    assert cap.provided_apis == []


# ---------------------------------------------------------------------------
# 18. metadata defaults to {}
# ---------------------------------------------------------------------------
def test_metadata_default_empty() -> None:
    reg = CapabilityRegistry()
    cap = reg.register("no_meta", "1.0")
    assert cap.metadata == {}


# ---------------------------------------------------------------------------
# 19. Capability.to_dict() has all required keys
# ---------------------------------------------------------------------------
def test_to_dict_keys() -> None:
    reg = CapabilityRegistry()
    cap = reg.register(
        "full",
        "1.2.3",
        provided_apis=["/x"],
        consumed_apis=["/y"],
        status="active",
        metadata={"owner": "agent-1"},
    )
    d = cap.to_dict()
    required = {
        "name", "version", "provided_apis", "consumed_apis",
        "status", "registered_at", "metadata",
    }
    assert required <= set(d.keys())
    assert d["name"] == "full"
    assert d["version"] == "1.2.3"
    assert d["provided_apis"] == ["/x"]
    assert d["consumed_apis"] == ["/y"]
    assert d["metadata"] == {"owner": "agent-1"}


# ---------------------------------------------------------------------------
# 20. Thread safety: 50 concurrent register() calls all persist
# ---------------------------------------------------------------------------
def test_thread_safety_concurrent_register() -> None:
    reg = CapabilityRegistry()
    errors: list[Exception] = []

    def _register(i: int) -> None:
        try:
            reg.register(f"module_{i:03d}", "1.0")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_register, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Thread errors: {errors}"
    assert len(reg.list_all()) == 50
